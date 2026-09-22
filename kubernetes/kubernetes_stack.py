import json
from aws_cdk import (
    Aws,
    aws_ec2 as ec2,
    aws_iam as _iam,
    Stack,
    aws_eks as eks,
    aws_sqs as sqs,   
    Tags,
    Duration
)
from constructs import Construct
from aws_cdk.lambda_layer_kubectl_v36 import KubectlV36Layer
from configs.roles import RoleStatements
from configs.helmvalues import HelmValues

   
class EksKarpenterStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, vpc: ec2.IVpc, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

         
        imported_vpc = vpc
        helm_values = HelmValues()
        clustername = "eks-spark-llm"
        role_statements = RoleStatements()

        # Set up an SQS queue for node disruption notifications
        self.node_disruption_queue = sqs.Queue(
            self,
            "NodeDisruptionQueue",
            queue_name="NodeDisruptionQueue",
            visibility_timeout=Duration.seconds(300),
            retention_period=Duration.days(14)
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
            min_size=1
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
   

        vpc_cni_role = role_statements.vpc_cni_pod_id_role_stmt(self)

        # vpc_cni addon
        vpc_cni_addon = eks.CfnAddon(
            self,
            "vpc-cni-addon",
            addon_name = "vpc-cni",
            namespace_config=eks.CfnAddon.NamespaceConfigProperty(
                namespace="kube-system"
            ),
            pod_identity_associations=[
                eks.CfnAddon.PodIdentityAssociationProperty(
                    role_arn=vpc_cni_role.role_arn,
                    service_account="aws-node"
                )
            ],
            cluster_name = clustername,
            addon_version = "v1.23.0-eksbuild.1",    
            resolve_conflicts="OVERWRITE",
            configuration_values=json.dumps(
                {"env":{"ENABLE_PREFIX_DELEGATION":"true",
                        "ENABLE_POD_ENI":"true",
                        "POD_SECURITY_GROUP_ENFORCING_MODE":"standard"},
                        "enableNetworkPolicy": "true"})
        )
        vpc_cni_addon.node.add_dependency(pod_identity_agent_addon)
       
        
        ebs_csi_addon_role = role_statements.ebs_csi_pod_id_role_stmt(self)

        ebs_csi_addon = eks.CfnAddon(
            self,
            "ebs-csi-driver-addon",
            addon_name = "aws-ebs-csi-driver",
            namespace_config=eks.CfnAddon.NamespaceConfigProperty(
                namespace="kube-system"
            ),
            pod_identity_associations=[
                eks.CfnAddon.PodIdentityAssociationProperty(
                    role_arn=ebs_csi_addon_role.role_arn,
                    service_account="ebs-csi-controller-sa"
                )
            ],
            cluster_name = clustername,
            addon_version = "v1.65.0-eksbuild.1",
            resolve_conflicts="OVERWRITE",
            
        )
        ebs_csi_addon.node.add_dependency(pod_identity_agent_addon)


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

   
        self.karpenter_controller_role = role_statements.karpenter_ctrl_pod_id_role_stmt(
            self,
            self.eks_cluster.cluster_name,
            self.node_disruption_queue.queue_arn
        )

        eks.CfnPodIdentityAssociation(
            self,
            "KarpenterControllerPodIdentityAssociation",
            cluster_name=self.eks_cluster.cluster_name,
            namespace="karpenter",
            service_account="karpenter-sa",
            role_arn=self.karpenter_controller_role.role_arn,
        )

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




    
        
        



        
        



        

        