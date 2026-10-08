import aws_cdk as cdk

from karpenter.karpenter_conf_stack import KarpenterConfigStack
from kubernetes.kubernetes_stack import EksKarpenterStack
from vpc.vpc_stack import VpcStack
from spark.spark_stack import SparkStack
from lustre.lustre_stack import LustreStack
from lustre.lustre_conf_stack import LustreConfigStack

from ecomm.ecomm_eks_stack import EcommEksStack
from documentdb.documentdb_stack import DocumentDBStack
from postgres.postgres_stack import PostgresDBStack
from postgres.postgres_conf_stack import PostgresConfigStack
from qdrant.qdrant_eks_stack import QdrantEksStack
from redis.redis_stack import RedisClusterStack
from zipkin.zipkin_eks_stack import ZipkinEksStack
from llm.llm_eks_stack import LlmEksStack
from tools.eks_tools_stack import EksToolsStack
from loadbalancer.eks_alb_stack import EksAlbStack



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
    description="This stack creates a VPC and flow logs for EKS cluster"
)

documentdb_stack = DocumentDBStack(
    app, 
    "DocumentDB", 
    vpc=vpc_stack.vpc, 
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="This stack creates a DocumentDB cluster for microservices"
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
    description="This stack creates a Postgres cluster for microservices"
)
postgres_stack.add_stack_dependency(vpc_stack)

postgres_config_stack = PostgresConfigStack(
    app, 
    "PostgresConfig", 
    vpc=vpc_stack.vpc,
    pg_info=postgres_stack.postgres_info,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
),
description="This stack configures the PostgresDb tables and schemas"
)
postgres_config_stack.add_stack_dependency(postgres_stack)

redis_stack = RedisClusterStack(
    app,
    "Redis",
    vpc=vpc_stack.vpc,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="This stack creates a Redis cluster for caching"
)
redis_stack.add_stack_dependency(vpc_stack)




kubernetes_stack = EksKarpenterStack(
    app, 
    "EksKarpenter", 
    vpc=vpc_stack.vpc, 
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="This stack creates a EKS cluster with Karpenter and LLM capabilities"
)
kubernetes_stack.add_stack_dependency(vpc_stack)

eks_karpenter_config_stack = KarpenterConfigStack(
    app, 
    "EksKarpenterConfig", 
    cluster=kubernetes_stack.eks_cluster,
    queue_name=kubernetes_stack.node_disruption_queue.queue_name,
    node_role_name=kubernetes_stack.karpenter_controller_role.role_name,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="This stack adds Karpenter manifests to the eks cluster"
)
eks_karpenter_config_stack.add_stack_dependency(kubernetes_stack)

eks_alb_stack = EksAlbStack(
    app,
    "EksAlb",
    cluster=kubernetes_stack.eks_cluster,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="This stack creates an ALB for the EKS cluster"
)
eks_alb_stack.add_stack_dependency(kubernetes_stack)

lustre_stack = LustreStack(
    app, 
    "Lustre",
    vpc=vpc_stack.vpc,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="This stack creates Fsx Lustre filesystem for llm model storage"
)
lustre_stack.add_stack_dependency(vpc_stack)


lustre_config_stack = LustreConfigStack(
    app, "LustreConfig", 
    cluster=kubernetes_stack.eks_cluster, 
    fsx_security_group=lustre_stack.fsx_security_group,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="This stack creates a EFS volume for spark storage"
)
lustre_config_stack.add_stack_dependency(kubernetes_stack)
lustre_config_stack.add_stack_dependency(lustre_stack)


llm_eks_stack = LlmEksStack(
    app,
    "LlmEks",
    cluster=kubernetes_stack.eks_cluster,
    lustre_info=lustre_stack.luster_info,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="This stack creates LLM models on EKS"
)
llm_eks_stack.add_stack_dependency(lustre_config_stack)


















qdrant_eks_stack = QdrantEksStack(
    app,
    "QdrantEks",
    cluster=kubernetes_stack.eks_cluster,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="This stack creates Qdrant on Eks"
)
qdrant_eks_stack.add_stack_dependency(kubernetes_stack)

spark_stack = SparkStack(
    app, 
    "Spark", 
    cluster=kubernetes_stack.eks_cluster,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="This stack creates a Spark Operator for running spark workloads"
)
spark_stack.add_stack_dependency(kubernetes_stack)

zipkin_eks_stack = ZipkinEksStack(
    app,
    "ZipkinEks",
    cluster=kubernetes_stack.eks_cluster,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="This stack creates Zipkin")
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
    description="This stack creates a Ecomm application on EKS"
)
ecomm_stack.add_stack_dependency(kubernetes_stack)
ecomm_stack.add_stack_dependency(postgres_stack)
ecomm_stack.add_stack_dependency(documentdb_stack)
ecomm_stack.add_stack_dependency(qdrant_eks_stack)
ecomm_stack.add_stack_dependency(redis_stack)
ecomm_stack.add_stack_dependency(zipkin_eks_stack)
ecomm_stack.add_stack_dependency(eks_alb_stack)


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
    description="This stack creates observation tools on EKS"
)
eks_tools_stack.add_stack_dependency(kubernetes_stack)



app.synth()
