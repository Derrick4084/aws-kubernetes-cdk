import ssl
import json
import hashlib
from aws_cdk import (
    Aws,
    aws_ec2 as ec2,
    aws_iam as _iam,
    Stack,
    aws_eks as eks,    
    CfnJson,
    Fn
)
from constructs import Construct
from aws_cdk.lambda_layer_kubectl_v32 import KubectlV32Layer
from configs.policies import RolePolicyStatements
from configs.helmvalues import HelmValues

   
def create_eks_thumbprint():
    cert = ssl.get_server_certificate(("oidc.eks.us-east-1.amazonaws.com", 443))
    der_cert = ssl.PEM_cert_to_DER_cert(cert)
    return hashlib.sha1(der_cert).hexdigest()

class KubernetesStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        thumbprint = create_eks_thumbprint()
        policy_statements = RolePolicyStatements()
        helm_values = HelmValues()
        clustername = "EKSSpark"
        vpc = ec2.Vpc.from_vpc_attributes(
            self, "VPC",
            vpc_id=Fn.import_value("VPCID"),
            availability_zones=[f"{Aws.REGION}-a", f"{Aws.REGION}-b"],
            private_subnet_ids=[
                Fn.import_value("PrivateSubnet1"),
                Fn.import_value("PrivateSubnet2")
            ],
            private_subnet_route_table_ids=[
                Fn.import_value("PrivateSubnetRouteTableID1"),
                Fn.import_value("PrivateSubnetRouteTableID2")
            ]
        )       
        eks_sec_group = ec2.SecurityGroup.from_security_group_id(self, "EKSSecurityGroup", Fn.import_value("EKSSecurityGroupID"))
               
        master_role = _iam.Role(
            self,
            "EksMasterRole",
            role_name="eks-admin-role",
            assumed_by=_iam.CompositePrincipal(
                _iam.ServicePrincipal("ec2.amazonaws.com"),
                _iam.ArnPrincipal(f"arn:aws:iam::{Aws.ACCOUNT_ID}:user/Derrick")
                # _iam.ArnPrincipal(f"arn:aws:iam::{Aws.ACCOUNT_ID}:user/{'add your eks admin name'}")
            ),
            managed_policies=policy_statements.eks_master_statement()               
        )
           
        cluster_role = _iam.Role(
            self,
            "EKSClusterRole",
            role_name="eks-cluster-role",
            assumed_by=_iam.ServicePrincipal(service="eks.amazonaws.com"),
            managed_policies=policy_statements.eks_cluster_statement()
        )
        
        worker_role = _iam.Role(
            self, "EKSWorkerRole", 
            role_name='eks-worker-role',
            assumed_by=_iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=policy_statements.eks_worker_statement()  
        )
        worker_role.attach_inline_policy(
            _iam.Policy(
                self, 
                "worker-role-policy",
                policy_name="amp-iamproxy-ingest-policy",
                statements=policy_statements.alb_loadbalancer_statement()
                )
            )
        
        self.eks_cluster = eks.Cluster(
            self,
            "EKSCluster",
            bootstrap_cluster_creator_admin_permissions=True,
            kubectl_layer=KubectlV32Layer(self, "kubectl"),
            version = eks.KubernetesVersion.V1_32,
            cluster_name = clustername,
            masters_role=master_role,
            role=cluster_role,
            vpc=vpc,
            vpc_subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)],
            security_group=eks_sec_group
        )
   
        # pod identity role
        self.pod_role = _iam.Role(
            self, "PodIdentityRole",
            assumed_by=_iam.ServicePrincipal("pods.eks.amazonaws.com"),
            description="IAM role for EKS Pod Identity"
        )
        self.pod_role.add_to_policy(_iam.PolicyStatement(
            effect=_iam.Effect.ALLOW,
            actions=[
                "s3:GetObject",
                "s3:ListBucket"
            ],
            resources=[
                "arn:aws:s3:::all-purpose-utility",
                "arn:aws:s3:::all-purpose-utility/*"
            ]
          )
        )

        # Create a service account with Pod Identity
        self.pod_service_account = eks.ServiceAccount(
            self, "ServiceAccount",
            cluster=self.eks_cluster,
            name="pod-identity-sa",
            namespace="kube-system",
            identity_type=eks.IdentityType.IRSA,
            annotations={
                "eks.amazonaws.com/role-arn": self.pod_role.role_arn
            }
        )

        # pod identity addon
        self.pod_identity_agent_addon = eks.CfnAddon(
            self,
            "eks-pod-identity-agent",
            addon_name = "eks-pod-identity-agent",
            cluster_name = clustername,
            addon_version = "v1.3.5-eksbuild.2",
            resolve_conflicts="OVERWRITE",
            service_account_role_arn = self.pod_service_account.role.role_arn,
            configuration_values=json.dumps(
                {
                  "agent": {
                      "additionalArgs": {"-b": "169.254.170.23"}
                    }
                }
            )
        )
        self.pod_identity_agent_addon.node.add_dependency(self.eks_cluster)

        # vpc_cni role
        self.vpc_cni_role = _iam.Role(
            self, "VpcCniRole",
            assumed_by=_iam.OpenIdConnectPrincipal(
                self.eks_cluster.open_id_connect_provider,
                conditions={
                    "StringEquals": CfnJson(self, 'aws-node-json',
                        value={
                            f"{self.eks_cluster.cluster_open_id_connect_issuer}:aud": "sts.amazonaws.com",
                            f"{self.eks_cluster.cluster_open_id_connect_issuer}:sub": "system:serviceaccount:kube-system:aws-node"
                        }
                    )
                }
            )
        )
        # Attach the required AWS managed policy for VPC CNI
        self.vpc_cni_role.add_managed_policy(
            _iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKS_CNI_Policy")
        )
        
        # vpc_cni addon
        vpc_cni_addon = eks.CfnAddon(
            self,
            "vpc-cni-addon",
            addon_name = "vpc-cni",
            service_account_role_arn=self.vpc_cni_role.role_arn,
            cluster_name = self.eks_cluster.cluster_name,
            addon_version = "v1.19.3-eksbuild.1",
            resolve_conflicts="OVERWRITE",
            configuration_values=json.dumps(
                {"env":{"ENABLE_PREFIX_DELEGATION":"true",
                        "ENABLE_POD_ENI":"true",
                        "POD_SECURITY_GROUP_ENFORCING_MODE":"standard"},
                        "enableNetworkPolicy": "true"})
        )
        vpc_cni_addon.node.add_dependency(self.eks_cluster)
       
        # ebscsi role
        self.ebs_csi_addon_role = _iam.Role(
            self, "ebs-csi-addon-role",
            assumed_by=_iam.OpenIdConnectPrincipal(
                self.eks_cluster.open_id_connect_provider,
                conditions={
                    "StringEquals": CfnJson(self, 'ebs-csi-controller-sa-json',
                        value={
                            f"{self.eks_cluster.cluster_open_id_connect_issuer}:aud": "sts.amazonaws.com",
                            f"{self.eks_cluster.cluster_open_id_connect_issuer}:sub": "system:serviceaccount:kube-system:ebs-csi-controller-sa"
                        }
                    )
                } 
            )                
        )      
        # Attach the required AWS managed policy for EBSCSI
        self.ebs_csi_addon_role.add_managed_policy(
            _iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEBSCSIDriverPolicy")
        )
        aws_ebs_csi_driver_addon = eks.CfnAddon(
            self,
            "ebs-csi-driver-addon",
            addon_name = "aws-ebs-csi-driver",
            cluster_name = self.eks_cluster.cluster_name,
            addon_version = "v1.41.0-eksbuild.1",
            resolve_conflicts="OVERWRITE",
            service_account_role_arn = self.ebs_csi_addon_role.role_arn
        )


        coredns_addon = eks.CfnAddon(
            self,
            "coredns-addon",
            addon_name = "coredns",
            cluster_name = self.eks_cluster.cluster_name,
            addon_version = "v1.11.4-eksbuild.2",
            resolve_conflicts="OVERWRITE",
        )
        coredns_addon.node.add_dependency(self.eks_cluster)

        kube_proxy_addon = eks.CfnAddon(
            self,
            "kube-proxy-addon",
            addon_name = "kube-proxy",
            cluster_name = clustername,
            addon_version = "v1.32.0-eksbuild.2",
            resolve_conflicts="OVERWRITE"
        )
        kube_proxy_addon.node.add_dependency(self.eks_cluster)

        # cluster autoscaler node group
        as_ng = self.eks_cluster.add_nodegroup_capacity(
            id="AutoScalingNodeGroup",
            desired_size=0,
            ami_type=eks.NodegroupAmiType.AL2_X86_64,
            instance_types=[ec2.InstanceType("m5.xlarge")],
            max_size=10,
            min_size=0,
            nodegroup_name="autoscaling-group",
            node_role=worker_role,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            labels={"node-type": "as-group"},
            tags={"k8s.io/cluster-autoscaler/enabled": "true",
                 f"k8s.io/cluster-autoscaler/{clustername}": f"{clustername}"
                }
        )

        super_user = _iam.User.from_user_arn(
            self,
            "iam-user",
            user_arn=f"arn:aws:iam::{Aws.ACCOUNT_ID}:user/Derrick"
        )

        self.eks_cluster.aws_auth.add_user_mapping(
            user=super_user,
            groups=["system:masters"],
            username=super_user.user_arn,
        )

        # cluster autoscaler role  
        cas_role = _iam.Role(self, 'cas-role', 
            assumed_by=_iam.OpenIdConnectPrincipal(
                self.eks_cluster.open_id_connect_provider,
                conditions={
                    "StringEquals": CfnJson(self, 'cluster-autoscaler-json',
                        value={
                            f"{self.eks_cluster.cluster_open_id_connect_issuer}:aud": "sts.amazonaws.com",
                            f"{self.eks_cluster.cluster_open_id_connect_issuer}:sub": "system:serviceaccount:kube-system:cluster-autoscaler"
                        }
                    )
                }                   
            )
        )
        cas_role.attach_inline_policy(
            _iam.Policy(self, "cas-inline-policy",
                policy_name="cas-inline-policy",
                statements=policy_statements.cas_policy_statetement()
            )
        )
        cas_role.node.add_dependency(self.eks_cluster)
        
        
        # Cluster autoscaler helm install
        cluster_autoscaler_helm = self.eks_cluster.add_helm_chart("ClusterAutoscaler",
            chart="cluster-autoscaler",
            repository="https://kubernetes.github.io/autoscaler",
            release="cluster-autoscaler",
            namespace="kube-system",
            version="9.46.4",
            values=helm_values.get_autoscaler_values(self.eks_cluster.cluster_name, f"{Aws.REGION}", f"{Aws.ACCOUNT_ID}")
            
        )
        cluster_autoscaler_helm.node.add_dependency(self.eks_cluster)

        