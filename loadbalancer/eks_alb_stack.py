from aws_cdk import (
    Aws,
    aws_eks as eks,
    aws_s3 as s3,
    aws_ec2 as ec2,
    aws_logs as logs,
    aws_iam as _iam,
    RemovalPolicy,    
    CfnOutput,
    Stack,
    Tags
)
from constructs import Construct

from configs.roles import RoleStatements
from configs.helmvalues import HelmValues

class EksAlbStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, cluster: eks.Cluster, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)


        role_statements = RoleStatements()
        helm_values = HelmValues()



        alb_role = role_statements.alb_pod_id_role_stmt(self)


        alb_sa = eks.ServiceAccount(
            self,
            "AlbServiceAccount",
            cluster=cluster,
            name="aws-alb-controller-sa",
            namespace="kube-system",
            labels={
                "app.kubernetes.io/component": "controller",
                "app.kubernetes.io/name": "aws-alb-controller-sa"
            }

        )

        alb_pod_identity = eks.CfnPodIdentityAssociation(
            self,
            "AlbPodIdentityAssociation",
            namespace="kube-system",
            cluster_name=cluster.cluster_name,
            role_arn=alb_role.role_arn,
            service_account="aws-alb-controller-sa"
        )


        cluster.add_helm_chart(
            "AwsLoadBalancer",
            chart="aws-load-balancer-controller",
            repository="https://aws.github.io/eks-charts",
            create_namespace=False,
            namespace="kube-system",
            version="3.5.0",
            values=helm_values.get_alb_values(
                clusername=cluster.cluster_name,
                service_acct_name="aws-alb-controller-sa"
            )
        )