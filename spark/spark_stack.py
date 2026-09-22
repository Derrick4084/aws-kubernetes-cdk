import yaml
from aws_cdk import ( 
    Stack,
    aws_eks as eks,
    aws_s3 as s3,      
    RemovalPolicy
)
from constructs import Construct
from configs.helmvalues import HelmValues
from configs.roles import RoleStatements

   
class SparkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, cluster: eks.Cluster, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
  
        helm_values = HelmValues()
        role_statements = RoleStatements()

        spark_bucket = s3.Bucket(
            self,
            "SparkBucket",
            bucket_name=f"{cluster.cluster_name}-eks-spark",
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY
        )


        spark_pod_role = role_statements.spark_pod_id_role_stmt(self, spark_bucket.bucket_arn)

        eks.CfnPodIdentityAssociation(
            self,
            "SparkPodIdentityAssociation",
            cluster_name=cluster.cluster_name,
            namespace="spark",
            service_account="spark-sa",
            role_arn=spark_pod_role.role_arn,
        )

        
        with open("spark/namespaces.yaml", "r") as f:
            manifests = [
                manifest
                for manifest in yaml.safe_load_all(f)
                if manifest is not None
            ]

        cluster.add_manifest(
            "SparkManifests",
            *manifests
        )

        
        cluster.add_helm_chart(
            "SparkOperator",
            chart="spark-operator",
            repository="https://kubeflow.github.io/spark-operator",
            create_namespace=True,
            namespace="spark-operator",
            version="2.5.2",
            values=helm_values.get_spark_values()
        )
