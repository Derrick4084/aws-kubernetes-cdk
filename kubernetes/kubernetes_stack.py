import json
import yaml
from aws_cdk import (
    Aws,
    aws_ec2 as ec2,
    aws_iam as _iam, 
    aws_eks as eks,
    aws_sqs as sqs,  
    Tags,
    Duration,
    CfnResource,
    CfnDeletionPolicy,
    Stack   
)
from constructs import Construct
from aws_cdk.lambda_layer_kubectl_v36 import KubectlV36Layer
from configs.roles import RoleStatements
from configs.helmvalues import HelmValues
from appconstructs.instance_profile_cleanup import InstanceProfileCleanup, ProfileProps

   
class EksStack(Stack):

    def __init__(
            self, 
            scope: Construct, 
            construct_id: str, 
            vpc: ec2.IVpc,
            lustre_info: dict,
            enable_alb: bool = False, 
            **kwargs
        ) -> None:
        super().__init__(scope, construct_id, **kwargs)


        # Function to set deletion policy to retain for all resources in a manifest
        def set_retain(manifest):
            for child in manifest.node.find_all():
                if isinstance(child, CfnResource):
                    child.cfn_options.deletion_policy = CfnDeletionPolicy.RETAIN


        # Import the VPC and Lustre information
        # Set cluster name and other variables
        imported_vpc = vpc
        helm_values = HelmValues()
        clustername = "eks-spark-llm"
        role_statements = RoleStatements()

        
        '''
        IAM roles for addons and pod identities
        '''
        ebs_csi_addon_role = role_statements.ebs_csi_pod_id_role_stmt(self)
        vpc_cni_role = role_statements.vpc_cni_pod_id_role_stmt(self)
        fsx_csi_controller_role = role_statements.fsx_csi_controller_role_stmt(self)
        external_secrets_role = role_statements.external_secrets_pod_id_role_stmt(self)
        ecomm_app_role = role_statements.ecomm_pod_id_role_stmt(self)
        
        karpenter_node_role = role_statements.karpenter_node_role_stmt(
            self, 
            clustername=clustername
        )
        
        model_storage_role = role_statements.model_storage_pod_id_role_stmt(
            self, 
            fsx_bucket_arn=lustre_info["fsx-bucket-arn"]
        )
        self.model_storage_role_name = model_storage_role.role_name


        '''
        SQS queue for Karpenter node disruption notifications
        '''
        node_disruption_queue = sqs.Queue(
            self,
            "NodeDisruptionQueue",
            queue_name=f"NodeDisruptionQueue-{clustername}",
            visibility_timeout=Duration.seconds(300),
            retention_period=Duration.days(14),
            enforce_ssl=True
        )

        '''
        Dedicated security group for Karpenter node discovery
        '''
        karpenter_sg = ec2.SecurityGroup(
            self,
            "KarpenterNodeSecurityGroup",
            vpc=imported_vpc,
            description="Security group for Karpenter provisioned nodes",
            allow_all_outbound=True
        )
        Tags.of(karpenter_sg).add("karpenter.sh/discovery", clustername)
        Tags.of(karpenter_sg).add("kubernetes.io/cluster/" + clustername, "owned")


        '''
        EKS Cluster
        '''
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
            _iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKSClusterPolicy")
        )
        Tags.of(self.eks_cluster.cluster_security_group).add("karpenter.sh/discovery", clustername)


        '''
        Allow all traffic from EKS cluster security group
        '''
        karpenter_sg.add_ingress_rule(
            peer=self.eks_cluster.cluster_security_group,
            connection=ec2.Port.all_traffic(),
            description="Allow all traffic from EKS cluster security group"
        )
        karpenter_sg.add_ingress_rule(
            peer=karpenter_sg,
            connection=ec2.Port.all_traffic(),
            description="Allow all traffic from EKS cluster security group"
        )

        '''
        Allow EKS control plane to register Karpenter nodes
        '''
        self.eks_cluster.cluster_security_group.add_ingress_rule(
            peer=karpenter_sg,
            connection=ec2.Port.tcp(443),
            description="Allow Karpenter nodes to register with EKS control plane"
        )

        '''
        Allow Karpenter nodes to communicate with Lustre file system
        '''
        lustre_sg = ec2.SecurityGroup.from_security_group_id(
            self, "LustreSG", lustre_info["fsx-sg-id"]
        )
        lustre_sg.add_ingress_rule(
            peer=karpenter_sg,
            connection=ec2.Port.tcp(988),
            description="Allow Lustre traffic from Karpenter nodes"
        )
        lustre_sg.add_ingress_rule(
            peer=karpenter_sg,
            connection=ec2.Port.tcp_range(1018, 1023),
            description="Allow Lustre traffic from Karpenter nodes"
        )

        self.eks_cluster.cluster_security_group.add_ingress_rule(
            peer=karpenter_sg,
            connection=ec2.Port.udp(53),
            description="Allow DNS UDP from Karpenter nodes"
        )

        # Allow DNS TCP from Karpenter nodes to CoreDNS
        self.eks_cluster.cluster_security_group.add_ingress_rule(
            peer=karpenter_sg,
            connection=ec2.Port.tcp(53),
            description="Allow DNS TCP from Karpenter nodes"
        )

              
        '''
        Create a launch template for the system node group
        '''
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


        '''
        Create a system node group for core services
        '''
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
            ),
            node_role=role_statements.system_node_group_role_stmt(self)
        )


        '''
        Tag subnets for Karpenter discovery
        '''
        for subnet in system_node_group.cluster.vpc.select_subnets(
            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
        ).subnets:
            Tags.of(subnet).add("karpenter.sh/discovery", clustername)


        '''
        Grant user access to EKS cluster
        '''
        self.eks_cluster.grant_access(
            id="DerrickEksAdminAccess",
            principal=f"arn:aws:iam::{Aws.ACCOUNT_ID}:user/Derrick", # add your eks admin name,
            access_policies=[
                eks.AccessPolicy.from_access_policy_name(
                    "AmazonEKSClusterAdminPolicy",
                    access_scope_type=eks.AccessScopeType.CLUSTER,)
            ]
        )


        '''
        Grant Karpenter node role access to EKS cluster
        '''
        self.eks_cluster.grant_access(
            id="KarpenterNodeRoleAccess",
            principal=karpenter_node_role.role_arn,
            access_policies=[],
            access_entry_type=eks.AccessEntryType.EC2_LINUX
        )


        '''
        Create Namespaces
        '''     
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

               
        '''
        Add required Amazon EKS add-ons
        '''
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
                        "POD_SECURITY_GROUP_ENFORCING_MODE": "standard",
                        "WARM_PREFIX_TARGET": "1",
                        "WARM_IP_TARGET": "5",
                        "MINIMUM_IP_TARGET": "2"
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
                    service_account="ebs-csi-controller-sa"
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
                    service_account="fsx-csi-controller-sa"
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
            addon_version = "v1.7.7-eksbuild.1",
            resolve_conflicts="OVERWRITE"
        )
        node_monitoring_addon.node.add_dependency(self.eks_cluster)


        '''
        This is where we define our Karpenter components
        Create the service account, roles and helm chart for karpenter
        using pod identity associations
        '''
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

        karpenter_ctrl_role = role_statements.karpenter_ctrl_pod_id_role_stmt(
            self, 
            cluster_name=clustername,
            cluster_arn=self.eks_cluster.cluster_arn,
            queue_arn=node_disruption_queue.queue_arn,
            karpenter_node_role_arn=karpenter_node_role.role_arn
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
        self.karpenter = self.eks_cluster.add_helm_chart(
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
        self.karpenter.node.add_dependency(karpenter_crds)


        '''
        Nvidia device plugin for GPU support
        '''
        nvidia_driver_helm = self.eks_cluster.add_helm_chart(
            "NvidiaDriver",
            chart="dra-driver-nvidia-gpu",
            repository="oci://registry.k8s.io/dra-driver-nvidia/charts/dra-driver-nvidia-gpu",
            namespace="nvidia",
            version="0.5.0",
            values=helm_values.get_nvidia_values()
        )
        nvidia_driver_helm.node.add_dependency(nvidia_ns)


        '''
        External Secrets Operator
        External secrets operator uses pod identity to assume roles
        along with service account to access secrets in AWS secrets manager
        '''
        external_secrets_sa = self.eks_cluster.add_manifest(
            "ExternalSecretsServiceAccount",
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {
                    "name": "external-secrets",
                    "namespace": "external-secrets",
                },
            }
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
        external_secrets_chart.node.add_dependency(external_secrets_sa)



        '''
        Fsx for Lustre components
        '''
        fsx_storage_sa = self.eks_cluster.add_manifest(
            "ModelStorageServiceAccount",
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {
                    "name": "model-storage",
                    "namespace": "ecomm",
                },
            }
        )
        fsx_storage_sa.node.add_dependency(ecomm_ns)

        fsx_storage_pod_identity = eks.CfnPodIdentityAssociation(
            self,
            "ModelStoragePodIdentityAssociation",
            cluster_name=clustername,
            namespace="ecomm",
            service_account="model-storage",
            role_arn=model_storage_role.role_arn,
        )
        fsx_storage_pod_identity.node.add_dependency(pod_identity_agent_addon)
        fsx_storage_pod_identity.node.add_dependency(fsx_storage_sa)



        '''
        Ecomm application service account and pod identity
        '''
        ecomm_app_sa = self.eks_cluster.add_manifest(
            "EcommAppServiceAccount",
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {
                    "name": "ecomm-app",
                    "namespace": "ecomm",
                },
            }
        )
        ecomm_app_sa.node.add_dependency(ecomm_ns)

        ecomm_pod_identity = eks.CfnPodIdentityAssociation(
            self,
            "EcommPodIdentityAssociation",
            cluster_name=clustername,
            namespace="ecomm",
            service_account="ecomm-app",
            role_arn=ecomm_app_role.role_arn,
        )
        ecomm_pod_identity.node.add_dependency(pod_identity_agent_addon)
        ecomm_pod_identity.node.add_dependency(ecomm_app_sa)


        """
        Karpenter NodeClasses and NodePools 
        for ecomm, embedding and LLM workloads
        """
        # Karpenter Nodeclasses  
        ecomm_nc = self.eks_cluster.add_manifest("ecomm-app-nodeclass", 
                yaml.safe_load(open("karpenter/ecomm-app-nc.yaml").read().format(
                    role_name=karpenter_node_role.role_name,
                    cluster_name=clustername
        )))
        ecomm_nc.node.add_dependency(self.karpenter)
        set_retain(ecomm_nc)

        embedding_nc = self.eks_cluster.add_manifest("embedding-nodeclass", 
                yaml.safe_load(open("karpenter/embedding-nc.yaml").read().format(
                    role_name=karpenter_node_role.role_name,    
                    cluster_name=clustername
        )))
        embedding_nc.node.add_dependency(self.karpenter)
        set_retain(embedding_nc)

        model_nc = self.eks_cluster.add_manifest("model-nodeclass", 
                yaml.safe_load(open("karpenter/llm-gpu-nc.yaml").read().format(
                    role_name=karpenter_node_role.role_name, 
                    cluster_name=clustername
        )))
        model_nc.node.add_dependency(self.karpenter)
        set_retain(model_nc)


        #  Karpenter Nodepools    
        ecomm_np = self.eks_cluster.add_manifest("ecomm-app-nodepool", 
                        yaml.safe_load(open("karpenter/ecomm-app-np.yaml").read()))
        ecomm_np.node.add_dependency(ecomm_nc)

        embedding_np = self.eks_cluster.add_manifest("embedding-nodepool", 
                yaml.safe_load(open("karpenter/embedding-np.yaml").read().format(
                    fsx_az=lustre_info["fsx-az"]
        )))
        embedding_np.node.add_dependency(embedding_nc)


        model_np = self.eks_cluster.add_manifest("model-nodepool", 
                yaml.safe_load(open("karpenter/llm-gpu-np.yaml").read().format(
                    fsx_az=lustre_info["fsx-az"]
        )))
        model_np.node.add_dependency(model_nc)


        """
        Persistant volumes and persistent volume claims for FSx for Lustre
        """         
        # Persistant volume for LLM and embeddings model download
        model_pv = self.eks_cluster.add_manifest("model-pv", 
                yaml.safe_load(open("lustre/lustre-pv.yaml").read().format(
                    fsx_id=lustre_info["fsx-id"], 
                    fsx_dns_name=lustre_info["fsx-dns-name"],
                    fsx_mount_name=lustre_info["fsx-mount-name"]
        )))
        model_pv.node.add_dependency(model_nc)
        model_pv.node.add_dependency(embedding_nc)

        # Persistant volume claim for LLM and embeddings model storage
        model_pvc = self.eks_cluster.add_manifest("model-pvc", 
                yaml.safe_load(open("lustre/lustre-pvc.yaml").read()))
        model_pvc.node.add_dependency(model_pv)

      
        '''
        Cleanup karpenter node role from instance profile
        We do this because Karpenter node role is attached to an instance profile
        which prevents the role from being deleted when the stack is destroyed.
        It uses a Contruct to create a custom resource that will remove the role 
        from the instance profile and delete the instance profile itself.
        '''
        profile_props = ProfileProps(
            role_name=karpenter_node_role.role_name
        )
        profile_cleanup = InstanceProfileCleanup(
            self, 
            "KarpenterNodeRoleCleanup",
            profile_props
        )
        profile_cleanup.node.add_dependency(karpenter_node_role)

       
        '''
        Application Load Balancer Controller
        '''
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
            alb.node.add_dependency(self.karpenter)





        

