import yaml
from aws_cdk import (
    Stack,
    aws_eks as eks,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct
from configs.roles import RoleStatements



class EksToolsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, 
                 cluster: eks.ICluster,
                 docdb_info: dict,
                 redis_info: dict, 
                 **kwargs
                ) -> None:
        super().__init__(scope, construct_id, **kwargs)


        role_statements = RoleStatements()

        tools_pod_id_role = role_statements.tools_pod_id_role_stmt(
            scope=self,
            clusterarn=cluster.cluster_arn,
            documentdb_info=docdb_info
        )
   
        pod_sa = eks.ServiceAccount(
            self,
            "MongoExpressServiceAccount",
            cluster=cluster,
            name="tools",
            namespace="ecomm-tools",
        )
        
        eks.CfnPodIdentityAssociation(
            self,
            "MongoExpressPodIdentityAssociation",
            cluster_name=cluster.cluster_name,
            namespace="ecomm-tools",
            service_account="tools",
            role_arn=tools_pod_id_role.role_arn,
        )

        mongo_secret = secretsmanager.Secret.from_secret_name_v2(
                    scope=self,
                    id="MongoExpressSecret",
                    secret_name=docdb_info["secret-name"]
                )
        documentdb_endpoint = mongo_secret.secret_value_from_json("documentdb_endpoint").unsafe_unwrap()
        port = mongo_secret.secret_value_from_json("port").unsafe_unwrap()
        username = mongo_secret.secret_value_from_json("username").unsafe_unwrap()
        password = mongo_secret.secret_value_from_json("password").unsafe_unwrap()

        documentdb_uri = (
            f"mongodb://{username}:{password}@"
            f"{documentdb_endpoint}:{port}/"
            f"?ssl=true"
            f"&tlsCAFile=/certs/ca-bundle.pem"
            f"&replicaSet=rs0"
            f"&readPreference=secondaryPreferred"
            f"&retryWrites=false"
        )

        
        with open("tools/mongo-express.yaml", "r") as f:
            mongo_express_manifests = [
                mongo_express_manifest
                for mongo_express_manifest in yaml.safe_load_all(
                    f.read().format(
                        mongo_uri=documentdb_uri
                    )
                )
                if mongo_express_manifest is not None
            ]

        for i, mongo_express_manifest in enumerate(mongo_express_manifests):
            m = cluster.add_manifest(f"MongoExpressManifest{i}", mongo_express_manifest)
            

        with open("tools/redis-insights.yaml", "r") as f:
            redis_insight_manifests = [
                redis_insight_manifest
                for redis_insight_manifest in yaml.safe_load_all(
                    f.read().format(
                        redis_host=redis_info["redis-endpoint"],
                    )
                )
                if redis_insight_manifest is not None
            ]

        for i, redis_insight_manifest in enumerate(redis_insight_manifests):
            m = cluster.add_manifest(f"RedisInsightManifest{i}", redis_insight_manifest)
            