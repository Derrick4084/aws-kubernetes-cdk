import yaml
from aws_cdk import (
    Stack,
    Aws,
    aws_eks as eks
)
from constructs import Construct
from configs.roles import RoleStatements


class EcommEksStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, 
                 cluster: eks.ICluster,
                 pg_info: dict,
                 docdb_info: dict,
                 embedding_info: dict,
                 microservices_info: dict,
                 model_info: dict,
                 qdrant_info: dict,
                 redis_info: dict,
                 zipkin_info: dict,
                 **kwargs
                ) -> None:
        super().__init__(scope, construct_id, **kwargs)


        role_statemens = RoleStatements()

        ecomm_pod_role = role_statemens.ecomm_pod_id_role_stmt(self)
        ecomm_pod_sa = eks.ServiceAccount(
            self,
            "EcommAppServiceAccount",
            cluster=cluster,
            name="ecomm",
            namespace="ecomm",
        ) 
        ecomm_pod_sa.node.add_dependency(ecomm_pod_role)


        ecomm_pod_identity = eks.CfnPodIdentityAssociation(
            self,
            "EcommPodIdentityAssociation",
            cluster_name=cluster.cluster_name,
            namespace="ecomm",
            service_account="ecomm",
            role_arn=ecomm_pod_role.role_arn,
        )
        ecomm_pod_identity.node.add_dependency(ecomm_pod_sa)


        with open("ecomm/image-pull.yaml", "r") as f:
            image_pull_manifests = [
                image_pull_manifest
                for image_pull_manifest in yaml.safe_load_all(
                    f.read().format(
                        region=Aws.REGION
                    )
                )
                if image_pull_manifest is not None
            ]

        previous_manifest = None

        for i, image_pull_manifest in enumerate(image_pull_manifests):
            manifest = cluster.add_manifest(f"ImagePullManifest{i}", image_pull_manifest)
            # manifest.node.add_dependency(ecomm_ns)
            if previous_manifest is not None:
                manifest.node.add_dependency(previous_manifest)

            previous_manifest = manifest

        
        image_pull_dependency = previous_manifest


        with open("ecomm/ecomm-service.yaml", "r") as f:
            ecomm_manifests = [
                ecomm_manifest
                for ecomm_manifest in yaml.safe_load_all(
                    f.read().format(
                        java_tool_options="-Xms512m -Xmx3200m -XX:+UseG1GC",
                        postgres_db_secret_name=pg_info["secret-name"],
                        documentdb_secret_name=docdb_info["secret-name"],
                        zipkin_host=zipkin_info["host"],
                        zipkin_port=zipkin_info["port"],
                        redis_host=redis_info["redis-endpoint"],
                        redis_port=redis_info["redis-port"],
                    )
                )
                if ecomm_manifest is not None
            ]

        for i, ecomm_manifest in enumerate(ecomm_manifests):
            manifest = cluster.add_manifest(f"EcommManifest{i}", ecomm_manifest)
            if image_pull_dependency is not None:
                manifest.node.add_dependency(image_pull_dependency)
                # manifest.node.add_dependency(secret_store)

            
        with open("ecomm/mcp-service.yaml", "r") as f:
            mcp_manifests = [
                mcp_manifest
                for mcp_manifest in yaml.safe_load_all(
                    f.read().format(
                        java_tool_options="-Xms512m -Xmx1536m -XX:+UseG1GC",
                        weather_api_secret_name="open-weather-api",
                        zipkin_host=zipkin_info["host"],
                        zipkin_port=zipkin_info["port"],
                        qdrant_host=qdrant_info["host"],
                        qdrant_port=qdrant_info["port"],
                    )
                )
                if mcp_manifest is not None
            ]
        for i, mcp_manifest in enumerate(mcp_manifests):
            manifest = cluster.add_manifest(f"McpManifest{i}", mcp_manifest)
            if image_pull_dependency is not None:
                manifest.node.add_dependency(image_pull_dependency)
                # manifest.node.add_dependency(secret_store)

            
            
        with open("ecomm/rag-service.yaml", "r") as f:
            rag_manifests = [
                rag_manifest
                for rag_manifest in yaml.safe_load_all(
                    f.read().format(
                        java_tool_options="-Xms512m -Xmx1536m -XX:+UseG1GC",
                        postgres_db_secret_name=pg_info["secret-name"],
                        mcp_host=microservices_info["mcp-host"],
                        mcp_port=microservices_info["mcp-port"],
                        embedding_host=embedding_info["host"],
                        embedding_port=embedding_info["port"],
                        model_host=model_info["host"],
                        model_port=model_info["port"],
                        qdrant_host=qdrant_info["host"],
                        qdrant_port=qdrant_info["port"],
                        zipkin_host=zipkin_info["host"],
                        zipkin_port=zipkin_info["port"],
                    )
                )
                if rag_manifest is not None
            ]   
        for i, rag_manifest in enumerate(rag_manifests):
            manifest = cluster.add_manifest(f"RagManifest{i}", rag_manifest)
            if image_pull_dependency is not None:
                manifest.node.add_dependency(image_pull_dependency)
                # manifest.node.add_dependency(secret_store)
            


        with open("ecomm/mail-service.yaml", "r") as f:
                    manifests = [
                        manifest
                        for manifest in yaml.safe_load_all(f)
                        if manifest is not None
                    ]
        cluster.add_manifest(
            "MailAppDeploymentManifest",
            *manifests
        )
