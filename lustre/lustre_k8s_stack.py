import yaml
from aws_cdk import (
    aws_ec2 as ec2,
    aws_iam as _iam,
    aws_s3 as s3,
    Stack,
    aws_eks as eks,
    aws_fsx as fsx,    
)
from constructs import Construct

   
class LustreK8sStack(Stack):

    def __init__(self, scope: Construct, construct_id: str,
            cluster: eks.Cluster,
            model_file_system: fsx.LustreFileSystem,
            data_bucket: s3.Bucket,
            fsx_security_group: ec2.ISecurityGroup,
            **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        
        ec2.CfnSecurityGroupIngress(
            self,
            "FsxLustreIngressRule",
            group_id=fsx_security_group.security_group_id,
            source_security_group_id=cluster.cluster_security_group_id,
            ip_protocol="tcp",
            from_port=988,
            to_port=1023,
            description="Allow Lustre traffic within VPC"
        )

        fsx_csi_controller_role = _iam.Role(
            self,
            "FsxCsiControllerRole",
            assumed_by=_iam.ServicePrincipal("pods.eks.amazonaws.com").with_session_tags(),
            description="IAM role for the AWS FSx CSI controller",
            managed_policies=[
                _iam.ManagedPolicy.from_aws_managed_policy_name("AmazonFSxFullAccess")
            ]
        )
                     
        eks.CfnAddon(
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
            cluster_name = cluster.cluster_name,
            addon_version = "v1.10.0-eksbuild.2",
            resolve_conflicts="OVERWRITE"
        )
        

       
        model_storage_pod_id_role = _iam.Role(
            self,
            "ModelStorageRole",
            assumed_by=_iam.ServicePrincipal("pods.eks.amazonaws.com").with_session_tags(),
            description="IAM role for model storage in S3"
        )
        model_storage_pod_id_role.add_to_policy(
            _iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:GetBucketLocation",
                ],
                resources=[
                    f"{data_bucket.bucket_arn}/*",
                    data_bucket.bucket_arn,
                ],
            )

        )

        model_storage_sa = eks.ServiceAccount(
            self,
            "ModelStorageServiceAccount",
            cluster=cluster,
            name="model-storage-sa",
            namespace="default",
        )
       
        eks.CfnPodIdentityAssociation(
            self,
            "ModelStoragePodIdentityAssociation",
            cluster_name=cluster.cluster_name,
            namespace=model_storage_sa.service_account_namespace,
            service_account="model-storage-sa",
            role_arn=model_storage_sa.role.role_arn,
        )
        

        hf_token = cluster.add_manifest("hugginface-token", 
                yaml.safe_load(open("lustre/huggingface-secret.yaml").read()))
        

        model_volume = cluster.add_manifest("model-fsx-volume", 
                yaml.safe_load(open("lustre/llm-pv.yaml").read().format(
                    fsx_id=model_file_system.file_system_id, 
                    fsx_dns_name=model_file_system.dns_name,
                    fsx_mount_name=model_file_system.mount_name
                )))
        model_volume.node.add_dependency(hf_token)

        model_volume_claim = cluster.add_manifest("model-fsx-claim", 
                yaml.safe_load(open("lustre/llm-pvc.yaml").read()))
        model_volume_claim.node.add_dependency(model_volume)


        # cluster.add_manifest("model-download", 
        #     yaml.safe_load(open("llm/model-download.yaml").read().format(      
        #         model_bucket=data_bucket.bucket_name,
        # )))

        # cluster.add_manifest("embeddings-download", 
        #     yaml.safe_load(open("embedding/embedding-download.yaml").read().format(      
        #         model_bucket=data_bucket.bucket_name,
        # )))


        # with open("llm/model-deployment.yaml", "r") as f:
        #     manifests = [
        #         manifest
        #         for manifest in yaml.safe_load_all(f)
        #         if manifest is not None
        #     ]
        # cluster.add_manifest(
        #     "ModelDeploymentManifest",
        #     *manifests
        # )


        # with open("embedding/embedding-deployment.yaml", "r") as f:
        #     manifests = [
        #         manifest
        #         for manifest in yaml.safe_load_all(f)
        #         if manifest is not None
        #     ]
        # cluster.add_manifest(
        #     "EmbeddingDeploymentManifest",
        #     *manifests
        # )
        