from configs.policies import RolePolicyStatements
from aws_cdk import (
    aws_iam as _iam,
    aws_eks as eks,  
    CfnJson,
    Aws
   
)


class RoleStatements:
    
    def __init__(self):
        pass


    @staticmethod
    def vpc_cni_pod_id_role_stmt(self):

        role = _iam.Role(
            self,
            "VpcCniPodIdentityRole",
            role_name="VpcCniPodIdentityRole",
            assumed_by=_iam.ServicePrincipal(
                "pods.eks.amazonaws.com"
            ).with_session_tags(),
        )

        role.add_managed_policy(
            _iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonEKS_CNI_Policy"
            )
        )

        return role


        
    @staticmethod
    def ebs_csi_pod_id_role_stmt(self):

        role = _iam.Role(
            self,
            "EbsCsiPodIdentityRole",
            role_name="EbsCsiPodIdentityRole",
            assumed_by=_iam.ServicePrincipal("pods.eks.amazonaws.com")
            .with_session_tags()
        )
        role.add_managed_policy(
            _iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AmazonEBSCSIDriverPolicy"
            )
        )

        return role
    

    @staticmethod
    def karpenter_node_role_stmt(self, clustername: str):

        policy_statements = RolePolicyStatements()

        role = _iam.Role(
            self,
            "KarpenterNodeRole",
            role_name=f"KarpenterNodeRole-{clustername}",
            assumed_by=_iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=policy_statements.karp_node_statement(),
        )

        _iam.CfnInstanceProfile(
            self,
            "KarpenterNodeInstanceProfile",
            roles=[role.role_name],
            instance_profile_name="KarpenterNodeInstanceProfile"
        )

        return role

        



    @staticmethod
    def karpenter_ctrl_pod_id_role_stmt(self, cluster_name: str, queue_arn: str):

        policy_statements = RolePolicyStatements()

        role = _iam.Role(
            self,
            "KarpenterPodIdentityRole",
            role_name="KarpenterPodIdentityRole",
            assumed_by=_iam.ServicePrincipal("pods.eks.amazonaws.com")
            .with_session_tags()
        )

        role.attach_inline_policy(
            _iam.Policy(self, "KarpenterControllerPolicy",
                policy_name="KarpenterControllerPolicy",
                statements=policy_statements.karp_controller_statement(
                    scope=self,
                    clustername=cluster_name, 
                    clusterarn=role.role_arn, 
                    rolearn=role.role_arn,
                    queuearn=queue_arn, 
                    region=f"{Aws.REGION}"
                )
            )
        )

        return role


    @staticmethod
    def spark_pod_id_role_stmt(self, bucket_arn: str):

        role = _iam.Role(
            self,
            "SparkPodIdentityRole",
            role_name="SparkPodIdentityRole",
            assumed_by=_iam.ServicePrincipal(
                "pods.eks.amazonaws.com"
            ).with_session_tags(),
        )

        role.add_to_policy(
        _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                ],
                resources=[
                    f"{bucket_arn}/*",
                ],
            )
        )
        role.add_to_policy(
            _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=[
                    "s3:GetBucketLocation",
                    "s3:ListBucket",
                ],
                resources=[
                    bucket_arn,
                ],
            )
        )

        return role
