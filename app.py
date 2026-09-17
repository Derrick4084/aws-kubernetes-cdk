import aws_cdk as cdk

from kubernetes.kubernetes_stack import EksKarpenterStack
from kubernetes.vpc_stack import VpcStack
from spark.spark_stack import SparkStack
from storage.lustre_stack import LustreStack
from storage.lustre_k8s_stack import LustreK8sStack

app = cdk.App()

vpc_stack = VpcStack(app, "VpcStack", env=cdk.Environment(
    account=cdk.Aws.ACCOUNT_ID,
    region=cdk.Aws.REGION,
    ),
    description="This stack creates a VPC and flow logs for EKS cluster"
)

kubernetes_stack = EksKarpenterStack(app, "EksKarpenterStack", vpc=vpc_stack.vpc, env=cdk.Environment(
    account=cdk.Aws.ACCOUNT_ID,
    region=cdk.Aws.REGION,
    ),
    description="This stack creates a EKS cluster with Karpenter and LLM capabilities"
)
kubernetes_stack.add_stack_dependency(vpc_stack)

lustre_stack = LustreStack(
    app, 
    "LustreStack",
    vpc=vpc_stack.vpc,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="This stack creates Fsx Lustre filesystem for llm model storage"

)
lustre_stack.add_stack_dependency(vpc_stack)


lustre_k8s_stack = LustreK8sStack(
    app, "LustreK8sStack", 
    cluster=kubernetes_stack.cluster, 
    data_bucket=lustre_stack.data_bucket, 
    model_file_system=lustre_stack.model_file_system,
    fsx_security_group=lustre_stack.fsx_security_group,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="This stack creates a EFS volume for spark storage"
)
lustre_k8s_stack.add_stack_dependency(kubernetes_stack)
lustre_k8s_stack.add_stack_dependency(lustre_stack)


spark_stack = SparkStack(
    app, 
    "SparkStack", 
    cluster=kubernetes_stack.cluster,
    env=cdk.Environment(
        account=cdk.Aws.ACCOUNT_ID,
        region=cdk.Aws.REGION,
    ),
    description="This stack creates a Spark Operator for running spark workloads"
)
spark_stack.add_stack_dependency(
    kubernetes_stack
    )


app.synth()
