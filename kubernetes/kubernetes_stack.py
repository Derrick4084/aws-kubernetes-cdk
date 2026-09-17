import json
import yaml
from aws_cdk import (
    Aws,
    aws_ec2 as ec2,
    aws_iam as _iam,
    Stack,
    aws_eks as eks,
    aws_sqs as sqs,   
    CfnJson,
    Tags,
    Duration
)
from constructs import Construct
from aws_cdk.lambda_layer_kubectl_v36 import KubectlV36Layer
from configs.policies import RolePolicyStatements
from configs.helmvalues import HelmValues

   
class EksKarpenterStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, vpc: ec2.IVpc, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

       
        policy_statements = RolePolicyStatements()
        helm_values = HelmValues()
        clustername = "eks-spark-llm"
        imported_vpc = vpc

        # eks_sec_group = ec2.SecurityGroup.from_security_group_id(
        #     self, 
        #     "EKSSecurityGroup", 
        #     Fn.import_value("EKSSecurityGroupID")
        # )

        # Set up an SQS queue for node disruption notifications
        node_disruption_queue = sqs.Queue(
            self,
            "NodeDisruptionQueue",
            queue_name="NodeDisruptionQueue",
            visibility_timeout=Duration.seconds(300),
            retention_period=Duration.days(14)
        )
            
        cluster_role = _iam.Role(
            self,
            "EKSClusterRole",
            role_name=f"eks-cluster-role-{clustername}",
            assumed_by=_iam.ServicePrincipal(service="eks.amazonaws.com"),
            managed_policies=policy_statements.eks_cluster_statement(),
        )
        cluster_role.add_to_policy(
            statement=_iam.PolicyStatement(
                actions=[
                    "sts:AssumeRole", 
                ],
                effect=_iam.Effect.ALLOW,
                resources=["*"]
            )
        )

        karpenter_node_role = _iam.Role(self, "KarpenterNodeRole",
            role_name="KarpenterNodeRole",
            assumed_by=_iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=policy_statements.karp_node_statement()
        )
        karpenter_node_role.add_to_policy(
            statement=_iam.PolicyStatement(
                actions=[
                    "sts:AssumeRole", 
                ],
                effect=_iam.Effect.ALLOW,
                resources=["*"]
            )
        )


        self.eks_cluster = eks.Cluster(
            self,
            "EKSCluster",
            bootstrap_cluster_creator_admin_permissions=True,
            kubectl_layer=KubectlV36Layer(self, "kubectl"),
            version = eks.KubernetesVersion.V1_36,
            cluster_name = clustername,
            authentication_mode=eks.AuthenticationMode.API_AND_CONFIG_MAP,
            endpoint_access=eks.EndpointAccess.PUBLIC_AND_PRIVATE,
            role=cluster_role,
            vpc=imported_vpc,
            vpc_subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)],
            default_capacity=0
        )

        system_node_group = eks.Nodegroup(self, "SystemNodeGroup",
            cluster=self.eks_cluster,
            nodegroup_name=f"{clustername}-system-nodegroup",
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            instance_types=[
                ec2.InstanceType("m5.xlarge"),
                ec2.InstanceType("m5a.xlarge")
            ],
            ami_type=eks.NodegroupAmiType.AL2023_X86_64_STANDARD,
            desired_size=1,
            max_size=1,
            min_size=1,
            node_role=karpenter_node_role
        )
        for subnet in system_node_group.cluster.vpc.select_subnets(
            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
        ).subnets:
            Tags.of(subnet).add("karpenter.sh/discovery", clustername)
        

        admin_user = _iam.User.from_user_arn(
            self,
            "AdminUser",
            user_arn=f"arn:aws:iam::{Aws.ACCOUNT_ID}:user/Derrick" # add your eks admin name
        )

        self.eks_cluster.grant_access(
            id="DerrickEksAdminAccess",
            principal=admin_user.user_arn,
            access_policies=[
                eks.AccessPolicy.from_access_policy_name(
                    "AmazonEKSClusterAdminPolicy",
                    access_scope_type=eks.AccessScopeType.CLUSTER,)
            ]
        )

        instance_profile = _iam.CfnInstanceProfile(
            self,
            "KarpenterNodeInstanceProfile",
            roles=[karpenter_node_role.role_name],
            instance_profile_name="KarpenterNodeInstanceProfile"
        )

        Tags.of(self.eks_cluster.cluster_security_group).add("karpenter.sh/discovery", clustername)
  

        # pod identity addon
        pod_identity_agent_addon = eks.CfnAddon(
            self,
            "eks-pod-identity-agent",
            addon_name = "eks-pod-identity-agent",
            cluster_name = clustername,
            addon_version = "v1.4.0-eksbuild.2",
            resolve_conflicts="OVERWRITE",
            configuration_values=json.dumps(
                {
                  "agent": {
                      "additionalArgs": {"-b": "169.254.170.23"}
                    }
                }
            )
        )
        pod_identity_agent_addon.node.add_dependency(self.eks_cluster)
   
        # vpc_cni role
        vpc_cni_role = _iam.Role(
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
        vpc_cni_role.add_managed_policy(
            _iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKS_CNI_Policy")
        )
        
        # vpc_cni addon
        vpc_cni_addon = eks.CfnAddon(
            self,
            "vpc-cni-addon",
            addon_name = "vpc-cni",
            service_account_role_arn=vpc_cni_role.role_arn,
            cluster_name = clustername,
            addon_version = "v1.23.0-eksbuild.1",    
            resolve_conflicts="OVERWRITE",
            configuration_values=json.dumps(
                {"env":{"ENABLE_PREFIX_DELEGATION":"true",
                        "ENABLE_POD_ENI":"true",
                        "POD_SECURITY_GROUP_ENFORCING_MODE":"standard"},
                        "enableNetworkPolicy": "true"})
        )
        vpc_cni_addon.node.add_dependency(self.eks_cluster)
       
        # ebscsi role
        ebs_csi_addon_role = _iam.Role(
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
        ebs_csi_addon_role.add_managed_policy(
            _iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEBSCSIDriverPolicy")
        )
        aws_ebs_csi_driver_addon = eks.CfnAddon(
            self,
            "ebs-csi-driver-addon",
            addon_name = "aws-ebs-csi-driver",
            cluster_name = clustername,
            addon_version = "v1.65.0-eksbuild.1",
            resolve_conflicts="OVERWRITE",
            service_account_role_arn = ebs_csi_addon_role.role_arn
        )

        coredns_addon = eks.CfnAddon(
            self,
            "coredns-addon",
            addon_name = "coredns",
            cluster_name = clustername,
            addon_version = "v1.14.3-eksbuild.16",
            resolve_conflicts="OVERWRITE",
        )
        coredns_addon.node.add_dependency(self.eks_cluster)

        kube_proxy_addon = eks.CfnAddon(
            self,
            "kube-proxy-addon",
            addon_name = "kube-proxy",
            cluster_name = clustername,
            addon_version = "v1.36.0-eksbuild.17",
            resolve_conflicts="OVERWRITE"
        )
        kube_proxy_addon.node.add_dependency(self.eks_cluster)


        node_monitoring_addon = eks.CfnAddon(
            self,
            "eks-node-monitoring-addon",
            addon_name = "eks-node-monitoring-agent",
            cluster_name = clustername,
            addon_version = "v1.7.0-eksbuild.1",
            resolve_conflicts="OVERWRITE"
        )
        node_monitoring_addon.node.add_dependency(self.eks_cluster)

        nvidia_driver_helm = self.eks_cluster.add_helm_chart(
            "NvidiaDriver",
            chart="dra-driver-nvidia-gpu",
            repository="oci://registry.k8s.io/dra-driver-nvidia/charts/dra-driver-nvidia-gpu",
            create_namespace=True,
            namespace="nvidia",
            version="0.5.0",
            values=helm_values.get_nvidia_values()
        )
        nvidia_driver_helm.node.add_dependency(self.eks_cluster)

        oidc_provider = self.eks_cluster.open_id_connect_provider
        
        karpenter_controller_role = _iam.Role(self, "KarpenterControllerRole",
            role_name="KarpenterControllerRole",
            assumed_by=_iam.FederatedPrincipal(oidc_provider.open_id_connect_provider_arn,
                        conditions={
                          "StringEquals": CfnJson(self, "KarpenterFederatedPrincipal",
                                value={
                                    f"{oidc_provider.open_id_connect_provider_issuer}:aud": "sts.amazonaws.com",
                                    f"{oidc_provider.open_id_connect_provider_issuer}:sub": "system:serviceaccount:karpenter:karpenter"
                                }
                            )  
                        },
                        assume_role_action="sts:AssumeRoleWithWebIdentity"
                )
        )

        karpenter_controller_role.attach_inline_policy(
            _iam.Policy(self, "KarpenterControllerPolicy",
                policy_name="KarpenterControllerPolicy",
                statements=policy_statements.karp_controller_statement( 
                    clustername=clustername, 
                    clusterarn=cluster_role.role_arn, 
                    rolearn=karpenter_controller_role.role_arn,
                    queuearn=node_disruption_queue.queue_arn, 
                    region=f"{Aws.REGION}"
                )
            )
        )
         
        self.eks_cluster.aws_auth.add_role_mapping(
            role=karpenter_controller_role,
            groups=["system:kube-system"],
            username="system:serviceaccount:karpenter:karpenter"
        )

        karpenter_crds = self.eks_cluster.add_helm_chart("KarpenterCRDs",
            chart="karpenter-crd",
            repository="oci://public.ecr.aws/karpenter/karpenter-crd",
            release="karpenter-crd",
            create_namespace=True,
            namespace="karpenter",
            version="1.14.1",
        )
    
        karpenter = self.eks_cluster.add_helm_chart(
            "Karpenter",
            chart="karpenter",
            repository="oci://public.ecr.aws/karpenter/karpenter",
            release="karpenter",
            namespace="karpenter",
            version="1.14.1",
            values=helm_values.get_karpenter_values(
                clustername=clustername, 
                cluster_endpoint=self.eks_cluster.cluster_endpoint,
                role_arn=karpenter_controller_role.role_arn,
                queue_name=node_disruption_queue.queue_name
            )
        )
        karpenter.node.add_dependency(karpenter_crds)


        node_class = self.eks_cluster.add_manifest("karpenter-nodeclass", 
                yaml.safe_load(open("karpenter/general-purpose-nc.yaml").read().format(role_name=karpenter_node_role.role_name, clustername=clustername)))
        node_class.node.add_dependency(karpenter)
        

        node_pool = self.eks_cluster.add_manifest("karpenter-nodepool", 
                yaml.safe_load(open("karpenter/general-purpose-np.yaml").read()))
        node_pool.node.add_dependency(karpenter)


        llm_node_class = self.eks_cluster.add_manifest("llm-nodeclass", 
                yaml.safe_load(open("llm/llm-gpu-nc.yaml").read().format(role_name=karpenter_node_role.role_name, clustername=clustername)))
        llm_node_class.node.add_dependency(karpenter)


        llm_node_pool = self.eks_cluster.add_manifest("llm-nodepool", 
                yaml.safe_load(open("llm/llm-gpu-np.yaml").read()))
        llm_node_pool.node.add_dependency(karpenter)


    @property
    def cluster(self):
        return self.eks_cluster



    
        
        



        
        



        

        