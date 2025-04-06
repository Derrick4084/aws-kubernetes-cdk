#!/usr/bin/env python3
import aws_cdk as cdk

from kubernetes.kubernetes_stack import KubernetesStack
from kubernetes.vpc_stack import VpcStack

app = cdk.App()

vpc_stack = VpcStack(app, "VpcStack", env=cdk.Environment(
    account=cdk.Aws.ACCOUNT_ID,
    region=cdk.Aws.REGION,
    ),
    description="This stack creates a VPC and flow logs for EKS cluster"
)

kubernetes_stack = KubernetesStack(app, "KubernetesStack", vpc=vpc_stack.vpc, env=cdk.Environment(
    account=cdk.Aws.ACCOUNT_ID,
    region=cdk.Aws.REGION,
    ),
    description="This stack creates a EKS cluster and a managed node group"
)
kubernetes_stack.add_dependency(vpc_stack)

app.synth()
