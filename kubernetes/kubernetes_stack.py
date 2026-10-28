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
from aws_cdk import aws_iam as iam

   
class EksStack(Stack):

    def __init__(
            self, 
            scope: Construct, 
            construct_id: str, 
            vpc: ec2.IVpc,
            lustre_sg_id: str,
            enable_alb: bool = False, 
            **kwargs
        ) -> None:
        super().__init__(scope, construct_id, **kwargs)


        imported_vpc = vpc
        helm_values = HelmValues()
        clustername = "eks-spark-llm"
        role_statements = RoleStatements()

        ebs_csi_addon_role = role_statements.ebs_csi_pod_id_role_stmt(self)
        vpc_cni_role = role_statements.vpc_cni_pod_id_role_stmt(self)
        fsx_csi_controller_role = role_statements.fsx_csi_controller_role_stmt(self)


        external_secrets_role = role_statements.external_secrets_pod_id_role_stmt(self)


        karpenter_node_role = role_statements.karpenter_node_role_stmt(
            self, 
            clustername=clustername
        )
        self.karpenter_node_role_name = karpenter_node_role.role_name



        # Set up an SQS queue for node disruption notifications
        node_disruption_queue = sqs.Queue(
            self,
            "NodeDisruptionQueue",
            queue_name=f"NodeDisruptionQueue-{clustername}",
            visibility_timeout=Duration.seconds(300),
            retention_period=Duration.days(14),
            enforce_ssl=True
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
            default_capacity=0,
            cluster_logging=[
                eks.ClusterLoggingTypes.API,
                eks.ClusterLoggingTypes.AUDIT,
                eks.ClusterLoggingTypes.AUTHENTICATOR,
                eks.ClusterLoggingTypes.CONTROLLER_MANAGER,
                eks.ClusterLoggingTypes.SCHEDULER
            ]
        )
        self.eks_cluster.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKSClusterPolicy")
        )
        Tags.of(self.eks_cluster.cluster_security_group).add("karpenter.sh/discovery", clustername)

        launch_template = ec2.LaunchTemplate(
            self,
            "SystemNodeLaunchTemplate",
            instance_metadata_tags=True,
            http_put_response_hop_limit=2,
            http_tokens=ec2.LaunchTemplateHttpTokens.REQUIRED,
            require_imdsv2=True,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=100,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        encrypted=True
                    )
                )
            ]
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
            desired_size=2,
            max_size=2,
            min_size=2,
            launch_template_spec=eks.LaunchTemplateSpec(
                id=launch_template.launch_template_id,
                version=launch_template.latest_version_number
            )
        )

        system_node_group.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonElasticContainerRegistryPublicReadOnly")
        )
        system_node_group.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryPullOnly")
        )
        system_node_group.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKSWorkerNodePolicy")
        )
        system_node_group.role.attach_inline_policy(
            iam.Policy(self, "SystemNodeGroupExtraPolicy",
                statements=[
                    iam.PolicyStatement(
                        actions=[
                            "ec2:DescribeInstanceTypeOfferings",
                            "ec2:DescribeInstanceTypes",
                            "ec2:DescribeInstanceStatus",
                            "ec2:DescribeSpotPriceHistory",
                            "pricing:GetProducts"
                        ],
                        resources=["*"]
                    )
                ]
            )
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

           
        ecomm_ns = self.eks_cluster.add_manifest(
            "EcommNamespace",
            {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {"name": "ecomm"},
            }
        )
        
        
        external_secrets_ns = self.eks_cluster.add_manifest(
            "ExternalSecretsNamespace",
            {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {"name": "external-secrets"},
            }
        )
        
        
        tools_ns = self.eks_cluster.add_manifest(
            "EcommToolsNamespace",
            {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {"name": "ecomm-tools"},
            }
        )
        

        karpenter_ns = self.eks_cluster.add_manifest(
            "KarpenterNamespace",
            {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {"name": "karpenter"},
            }
        )


        nvidia_ns = self.eks_cluster.add_manifest(
            "NvidiaNamespace",
            {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {"name": "nvidia"},
            }
        )

        
        karpenter_sa = self.eks_cluster.add_manifest(
            "KarpenterServiceAccount",
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {
                    "name": "karpenter",
                    "namespace": "karpenter",
                },
            }
        )
        karpenter_sa.node.add_dependency(karpenter_ns)
        
            
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
            configuration_values=json.dumps({
                    "env": {
                        "ENABLE_PREFIX_DELEGATION": "true",
                        "ENABLE_POD_ENI": "true",
                        "POD_SECURITY_GROUP_ENFORCING_MODE": "standard"
                    },
                    "enableNetworkPolicy": "true"
                }
            )
        )
        vpc_cni_addon.add_resource_dependency(pod_identity_agent_addon)
       
           
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
                    service_account="ebs-csi-controller"
                )
            ],
            cluster_name = clustername,
            addon_version = "v1.65.0-eksbuild.1",
            resolve_conflicts="OVERWRITE",
            
        )
        ebs_csi_addon.add_resource_dependency(pod_identity_agent_addon)


        fsx_csi_addon = eks.CfnAddon(
            self,
            "fsx-csi-driver-addon",
            addon_name = "aws-fsx-csi-driver",
            pod_identity_associations=[
                eks.CfnAddon.PodIdentityAssociationProperty(
                    role_arn=fsx_csi_controller_role.role_arn,
                    service_account="fsx-csi-controller"
                )
            ],
            namespace_config=eks.CfnAddon.NamespaceConfigProperty(
                namespace="kube-system"
            ),
            cluster_name = clustername,
            addon_version = "v1.10.0-eksbuild.2",
            resolve_conflicts="OVERWRITE"
        )
        fsx_csi_addon.node.add_dependency(pod_identity_agent_addon)


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
            addon_version = "v1.7.2-eksbuild.1",
            resolve_conflicts="OVERWRITE"
        )
        node_monitoring_addon.node.add_dependency(self.eks_cluster)


        ec2.CfnSecurityGroupIngress(
            self,
            "FsxLustreIngressRule",
            group_id=lustre_sg_id,
            source_security_group_id=self.eks_cluster.cluster_security_group_id,
            ip_protocol="tcp",
            from_port=988,
            to_port=1023,
            description="Allow Lustre traffic within VPC"
        )

        karpenter_ctrl_role = role_statements.karpenter_ctrl_pod_id_role_stmt(
            self, 
            cluster_name=clustername,
            cluster_arn=self.eks_cluster.cluster_arn,
            queue_arn=node_disruption_queue.queue_arn,
            system_node_group_role_arn=system_node_group.role.role_arn
        )
        karpenter_ctrl_role.node.add_dependency(self.eks_cluster)
        
        karpenter_crds = self.eks_cluster.add_helm_chart("KarpenterCRDs",
            chart="karpenter-crd",
            repository="oci://public.ecr.aws/karpenter/karpenter-crd",
            release="karpenter-crd",
            namespace="karpenter",
            version="1.14.1",
        )
        karpenter_crds.node.add_dependency(karpenter_ns)
       
        karpenter_pod_identity = eks.CfnPodIdentityAssociation(
            self,
            "KarpenterPodIdentityAssociation",
            namespace="karpenter",
            cluster_name=clustername,
            role_arn=karpenter_ctrl_role.role_arn,
            service_account="karpenter"
        )
        karpenter_pod_identity.node.add_dependency(
            pod_identity_agent_addon
        )
        karpenter_pod_identity.node.add_dependency(
            karpenter_sa
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
                queue_name=node_disruption_queue.queue_name,
                aws_region=Aws.REGION
            )
        )
        karpenter.node.add_dependency(karpenter_crds)

        
        nvidia_driver_helm = self.eks_cluster.add_helm_chart(
            "NvidiaDriver",
            chart="dra-driver-nvidia-gpu",
            repository="oci://registry.k8s.io/dra-driver-nvidia/charts/dra-driver-nvidia-gpu",
            namespace="nvidia",
            version="0.5.0",
            values=helm_values.get_nvidia_values()
        )
        nvidia_driver_helm.node.add_dependency(nvidia_ns)


        external_secrets_sa = eks.ServiceAccount(
            self,
            "ExternalSecretsServiceAccount",
            cluster=self.eks_cluster,
            name="external-secrets",
            namespace="external-secrets",
        )
        external_secrets_sa.node.add_dependency(external_secrets_ns)

        external_pod_identity = eks.CfnPodIdentityAssociation(
            self,
            "ExternalSecretsPodIdentityAssociation",
            cluster_name=clustername,
            namespace="external-secrets",
            service_account="external-secrets",
            role_arn=external_secrets_role.role_arn,
        )
        external_pod_identity.node.add_dependency(pod_identity_agent_addon)
        external_pod_identity.node.add_dependency(external_secrets_sa)


        external_secrets_chart = self.eks_cluster.add_helm_chart(
            "ExternalSecretsOperator",
            repository="https://charts.external-secrets.io",
            chart="external-secrets",
            release="external-secrets",
            namespace="external-secrets",
            create_namespace=False,
            values={
                "installCRDs": True,
                "serviceAccount": {
                    "create": False,
                    "name": "external-secrets",
                },
            },
        )
        external_secrets_chart.node.add_dependency(external_pod_identity)


        if enable_alb:

            alb_role = role_statements.alb_pod_id_role_stmt(self)
            alb_sa = self.eks_cluster.add_manifest(
                "AlbServiceAccount",
                {
                    "apiVersion": "v1",
                    "kind": "ServiceAccount",
                    "metadata": {
                        "name": "aws-alb-controller",
                        "namespace": "kube-system",
                        "labels": {
                            "app.kubernetes.io/component": "controller",
                            "app.kubernetes.io/name": "aws-load-balancer-controller",
                        },
                    },
                },
            )
            alb_pod_identity = eks.CfnPodIdentityAssociation(
                self,
                "AlbPodIdentityAssociation",
                namespace="kube-system",
                cluster_name=clustername,
                role_arn=alb_role.role_arn,
                service_account="aws-alb-controller"
            )
            alb_pod_identity.node.add_dependency(alb_role)
            alb_pod_identity.node.add_dependency(pod_identity_agent_addon)
            alb_pod_identity.node.add_dependency(alb_sa)


            alb = self.eks_cluster.add_helm_chart(
                "AwsLoadBalancer",
                chart="aws-load-balancer-controller",
                repository="https://aws.github.io/eks-charts",
                namespace="kube-system",
                release="aws-load-balancer-controller",
                version="3.5.0",
                values=helm_values.get_alb_values(
                    clustername=clustername,
                    service_acct_name="aws-alb-controller",
                    vpc_id=imported_vpc.vpc_id     
                )
            )
            alb.node.add_dependency(karpenter)