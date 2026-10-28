import aws_cdk as cdk

from kubernetes.kubernetes_stack import EksStack
from vpc.vpc_stack import VpcStack
from spark.spark_stack import SparkStack
from lustre.lustre_stack import LustreStack
from ecomm.ecomm_eks_stack import EcommEksStack
from documentdb.documentdb_stack import DocumentDBStack
from postgres.postgres_stack import PostgresDBStack
from qdrant.qdrant_eks_stack import QdrantEksStack
from redis.redis_stack import RedisClusterStack
from zipkin.zipkin_eks_stack import ZipkinEksStack
from llm.llm_eks_stack import LlmEksStack
from tools.eks_tools_stack import EksToolsStack




app = cdk.App()

model_info = {
    "host": "vllm-svc.ecomm.svc.cluster.local",
    "port": "8081"
}

embedding_info = {
    "host": "embed-svc.ecomm.svc.cluster.local",
    "port": "8082"
}

microservices_info = {
    "ecomm-host": "ecomm-svc.ecomm.svc.cluster.local",
    "ecomm-port": "8079",
    "mcp-host": "mcp-svc.ecomm.svc.cluster.local",
    "mcp-port": "8075",
    "rag-host": "rag-svc.ecomm.svc.cluster.local",
    "rag-port": "8080",
    "redis-insights-host": "redis-insight-svc.ecomm-tools.svc.cluster.local",
    "redis-insights-port": "5540",
    "mongo-express-host": "mongo-express-svc.ecomm-tools.svc.cluster.local",
    "mongo-express-port": "8083"
}

vpc_stack = VpcStack(app, "Vpc", env=cdk.Environment(
    account=cdk.Aws.ACCOUNT_ID,
    region=cdk.Aws.REGION,
    ),
    description="VPC and flow logs for EKS cluster"
)

# Stacks that depend on the VPC stack

documentdb_stack = DocumentDBStack(
    app, 
    "DocumentDB", 
    vpc=vpc_stack.vpc, 
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="DocumentDB cluster for microservices"
)
documentdb_stack.add_stack_dependency(vpc_stack)

postgres_stack = PostgresDBStack(
    app, 
    "Postgres", 
    vpc=vpc_stack.vpc, 
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="Postgres cluster for microservices"
)
postgres_stack.add_stack_dependency(vpc_stack)


redis_stack = RedisClusterStack(
    app,
    "Redis",
    vpc=vpc_stack.vpc,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="Redis cluster for caching"
)
redis_stack.add_stack_dependency(vpc_stack)


lustre_stack = LustreStack(
    app, 
    "Lustre",
    vpc=vpc_stack.vpc,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="Fsx Lustre filesystem for LLM storage"
)
lustre_stack.add_stack_dependency(vpc_stack)


kubernetes_stack = EksStack(
    app, 
    "Eks", 
    vpc=vpc_stack.vpc,
    lustre_sg_id=lustre_stack.fsx_security_group.security_group_id,
    enable_alb=True,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="EKS cluster for Ecomm application and LLM capabilities"
)
kubernetes_stack.add_stack_dependency(lustre_stack)


llm_eks_stack = LlmEksStack(
    app,
    "Llm",
    cluster=kubernetes_stack.eks_cluster,
    lustre_info=lustre_stack.luster_info,
    karpenter_node_role_name=kubernetes_stack.karpenter_node_role_name,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="LLM and Embedding models download on EKS"
)
llm_eks_stack.add_stack_dependency(kubernetes_stack)


qdrant_eks_stack = QdrantEksStack(
    app,
    "Qdrant",
    cluster=kubernetes_stack.eks_cluster,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="Qdrant vector database for EKS cluster"
)
qdrant_eks_stack.add_stack_dependency(kubernetes_stack)


zipkin_eks_stack = ZipkinEksStack(
    app,
    "Zipkin",
    cluster=kubernetes_stack.eks_cluster,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="Zipkin observability for EKS cluster"
)
zipkin_eks_stack.add_stack_dependency(kubernetes_stack)


ecomm_stack = EcommEksStack(
    app,
    "EcommEks",
    cluster=kubernetes_stack.eks_cluster,
    pg_info=postgres_stack.postgres_info,
    docdb_info=documentdb_stack.docdb_info,
    embedding_info=embedding_info,
    model_info=model_info,
    microservices_info=microservices_info,
    qdrant_info=qdrant_eks_stack.qdrant_info,
    redis_info=redis_stack.redis_info,
    zipkin_info=zipkin_eks_stack.zipkin_info,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="Ecomm application on EKS"
)
ecomm_stack.add_stack_dependency(llm_eks_stack)
ecomm_stack.add_stack_dependency(qdrant_eks_stack)
ecomm_stack.add_stack_dependency(zipkin_eks_stack)


eks_tools_stack = EksToolsStack(
    app,
    "EcommAppTools",
    cluster=kubernetes_stack.eks_cluster,
    docdb_info=documentdb_stack.docdb_info,
    redis_info=redis_stack.redis_info,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="Observation tools for EKS cluster"
)
eks_tools_stack.add_stack_dependency(ecomm_stack)


# spark_stack = SparkStack(
#     app, 
#     "Spark", 
#     cluster=kubernetes_stack.eks_cluster,
#     env=cdk.Environment(
#         account=cdk.Aws.ACCOUNT_ID,
#         region=cdk.Aws.REGION,
#     ),
#     description="Spark Operator for running spark workloads"
# )
# spark_stack.add_stack_dependency(kubernetes_stack)


app.synth()
