import yaml
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_eks as eks,
    aws_iam as _iam,
    aws_s3 as s3,
    Aws
)
from constructs import Construct


class LlmEksStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, 
            cluster: eks.Cluster,
            lustre_info: dict, 
            **kwargs
        ) -> None:
        super().__init__(scope, construct_id, **kwargs)


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
                    f"{lustre_info['fsx-bucket-arn']}/*",
                    lustre_info['fsx-bucket-arn'],
                ],
            )

        )

        model_storage_pod_id_role.add_to_policy(
            _iam.PolicyStatement(
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret"
                ],
                effect=_iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:secretsmanager:{Aws.REGION}:{Aws.ACCOUNT_ID}:secret:open-weather-api*"
                ]
            ),
        )

        model_storage_sa = eks.ServiceAccount(
            self,
            "ModelStorageServiceAccount",
            cluster=cluster,
            name="model-storage-sa",
            namespace="ecomm",
        )
        
        eks.CfnPodIdentityAssociation(
            self,
            "ModelStoragePodIdentityAssociation",
            cluster_name=cluster.cluster_name,
            namespace=model_storage_sa.service_account_namespace,
            service_account="model-storage-sa",
            role_arn=model_storage_pod_id_role.role_arn,
        )


        model_volume = cluster.add_manifest("model-fsx-volume", 
                yaml.safe_load(open("lustre/llm-pv.yaml").read().format(
                    fsx_id=lustre_info["fsx-id"], 
                    fsx_dns_name=lustre_info["fsx-dns-name"],
                    fsx_mount_name=lustre_info["fsx-mount-name"]
                )))

        model_volume_claim = cluster.add_manifest("model-fsx-claim", 
                yaml.safe_load(open("lustre/llm-pvc.yaml").read()))
        model_volume_claim.node.add_dependency(model_volume)


        model_download = cluster.add_manifest("model-download", 
            yaml.safe_load(open("llm/model-download.yaml").read().format(      
                model_bucket=lustre_info['fsx-bucket-name'],
        )))

        embedding_download = cluster.add_manifest("embeddings-download", 
            yaml.safe_load(open("embedding/embedding-download.yaml").read().format(      
                model_bucket=lustre_info['fsx-bucket-name'],
        )))


        with open("llm/model-deployment.yaml", "r") as f:
            model_deploy_manifests = [
                manifest
                for manifest in yaml.safe_load_all(f)
                if manifest is not None
            ]

        with open("embedding/embedding-deployment.yaml", "r") as f:
            embedding_deploy_manifests = [
                manifest
                for manifest in yaml.safe_load_all(f)
                if manifest is not None
            ] 
    
          
        cluster.add_manifest(
            "ModelDeploymentManifest",
            *model_deploy_manifests
        ).node.add_dependency(model_download)


        cluster.add_manifest(
            "EmbeddingDeploymentManifest",
            *embedding_deploy_manifests
        ).node.add_dependency(embedding_download)

    
                