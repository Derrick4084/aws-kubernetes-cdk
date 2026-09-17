import yaml
from aws_cdk import ( 
    aws_iam as _iam,
    Stack,
    aws_eks as eks,
    aws_sqs as sqs,
    aws_s3 as s3,      
    RemovalPolicy
)
from constructs import Construct
from configs.helmvalues import HelmValues

   
class SparkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, cluster: eks.Cluster, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)


        clustername = cluster.cluster_name
        eks_cluster = cluster
        helm_values = HelmValues()


        spark_bucket = s3.Bucket(
            self,
            "SparkBucket",
            bucket_name=f"{clustername}-eks-spark",
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY
        )

        spark_pod_role = _iam.Role(
            self,
            "SparkPodIdentityRole",
            assumed_by=_iam.ServicePrincipal("pods.eks.amazonaws.com"),
            description="IAM role for Spark pods",
        )
        spark_pod_role.add_to_policy(
            _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                ],
                resources=[
                    f"{spark_bucket.bucket_arn}/*",
                ],
            )
        )
        spark_pod_role.add_to_policy(
            _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=[
                    "s3:GetBucketLocation",
                    "s3:ListBucket",
                ],
                resources=[
                    spark_bucket.bucket_arn,
                ],
            )
        )

        with open("spark/namespaces.yaml", "r") as f:
            manifests = [
                manifest
                for manifest in yaml.safe_load_all(f)
                if manifest is not None
            ]

        spark_namespaces = eks_cluster.add_manifest(
            "SparkManifests",
            *manifests
        )

        # Kubernetes ServiceAccount used by Spark driver/executor pods
        spark_service_account = eks.ServiceAccount(
            self,
            "SparkServiceAccount",
            cluster=eks_cluster,
            name="spark-sa",
            namespace="spark"
        )
        spark_service_account.node.add_dependency(spark_namespaces)


        spark_pod_identity = eks.CfnPodIdentityAssociation(
            self,
            "SparkPodIdentityAssociation",
            cluster_name=clustername,
            namespace=spark_service_account.service_account_namespace,
            service_account=spark_service_account.service_account_name,
            role_arn=spark_pod_role.role_arn,
        )
        spark_pod_identity.node.add_dependency(
            spark_service_account
        )

        spark_operator_helm = eks_cluster.add_helm_chart(
            "SparkOperator",
            chart="spark-operator",
            repository="https://kubeflow.github.io/spark-operator",
            create_namespace=True,
            namespace="spark-operator",
            version="2.5.2",
            values=helm_values.get_spark_values()
        )
