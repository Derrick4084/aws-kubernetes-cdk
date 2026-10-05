import yaml
from aws_cdk import (
    Stack,
    Aws,
    aws_eks as eks,
    aws_iam as _iam,
)
from constructs import Construct
from configs.roles import RoleStatements


class EcommEksStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, 
                 cluster: eks.Cluster,
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






        external_secrets_ns = cluster.add_manifest(
            "ExternalSecretsNamespace",
            yaml.safe_load(open("ecomm/external-secrets-ns.yaml").read())
        )

        ecomm_ns = cluster.add_manifest(
            "EcommAppNamespace",
            yaml.safe_load(open("ecomm/ecomm-ns.yaml").read())
        )

        

        
        

        






       
        external_secrets_role = _iam.Role(
            self, "ExternalSecretsPodIdentityRole",
            role_name="ExternalSecretsPodIdentityRole",
            assumed_by=_iam.ServicePrincipal(
                "pods.eks.amazonaws.com"
            ).with_session_tags(),
            description="Pod Identity role for External Secrets Operator",
        )
        external_secrets_role.add_to_policy(
            _iam.PolicyStatement(
                sid="ReadEcommGhcrSecret",
                effect=_iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret",
                ],
                resources=[
                    f"arn:aws:secretsmanager:{Aws.REGION}:{Aws.ACCOUNT_ID}:secret:github-secret-token-*"
                ],
            )
        )
        
        external_secrets_sa = eks.ServiceAccount(
            self,
            "ExternalSecretsServiceAccount",
            cluster=cluster,
            name="external-secrets-sa",
            namespace="external-secrets",
        )
        external_secrets_sa.node.add_dependency(external_secrets_ns)

        external_pod_identity = eks.CfnPodIdentityAssociation(
            self,
            "ExternalSecretsPodIdentityAssociation",
            cluster_name=cluster.cluster_name,
            namespace=external_secrets_sa.service_account_namespace,
            service_account="external-secrets-sa",
            role_arn=external_secrets_role.role_arn,
        )
        external_pod_identity.node.add_dependency(external_secrets_sa)

        external_secrets_chart = cluster.add_helm_chart(
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
                    "name": "external-secrets-sa",
                },
            },
        )
        external_secrets_chart.node.add_dependency(external_secrets_ns)


        cluster_secret_store = cluster.add_manifest("ClusterSecretStore", 
            yaml.safe_load(open("ecomm/cluster-secret-store.yaml").read().format(
                    region=Aws.REGION
                )
            )
        )
        cluster_secret_store.node.add_dependency(external_secrets_chart)


        image_pull = cluster.add_manifest("GhcrImagePull", 
            yaml.safe_load(open("ecomm/image-pull.yaml").read()))
        
        image_pull.node.add_dependency(ecomm_ns)
        image_pull.node.add_dependency(cluster_secret_store)




        
        




        
        
        
        
        
        
        
        
        ecomm_role_statements = RoleStatements()

        ecomm_pod_role = ecomm_role_statements.ecomm_pod_id_role_stmt(self)

        ecomm_pod_sa = eks.ServiceAccount(
            self,
            "EcommAppServiceAccount",
            cluster=cluster,
            name="ecomm-sa",
            namespace="ecomm",
        )
        ecomm_pod_sa.node.add_dependency(ecomm_ns)
        
        ecomm_pod_identity = eks.CfnPodIdentityAssociation(
            self,
            "EcommPodIdentityAssociation",
            cluster_name=cluster.cluster_name,
            namespace=ecomm_pod_sa.service_account_namespace,
            service_account="ecomm-sa",
            role_arn=ecomm_pod_role.role_arn,
        )
        ecomm_pod_identity.node.add_dependency(ecomm_pod_sa)

        



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
            cluster.add_manifest(f"EcommManifest{i}", ecomm_manifest)

        


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
            cluster.add_manifest(f"McpManifest{i}", mcp_manifest)


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
            cluster.add_manifest(f"RagManifest{i}", rag_manifest)


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