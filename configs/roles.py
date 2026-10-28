from aws_cdk import (
    aws_iam as _iam,
    Aws   
)
from constructs import Construct
from configs.policies import RolePolicyStatements


class RoleStatements:
    
    def __init__(self):
        pass


    def get_principal(self, scope: Construct, role_name: str) -> _iam.Role:
        principal = _iam.Role(scope, f"{role_name}",
            assumed_by=_iam.ServicePrincipal(
                "pods.eks.amazonaws.com"
            ).with_session_tags(),
            role_name=f"{role_name}",
            description="Pod Identity role for observation tools",
        )
        return principal


    def tools_pod_id_role_stmt(
            self,
            scope: Construct,
            clusterarn: str,
            documentdb_info: dict, 
        ) -> _iam.Role:

        resource_id = documentdb_info["resource_id"]
        user = documentdb_info["username"]

        role = self.get_principal(scope, role_name="ToolsPodIdentityRole")
        role.add_to_policy(
            _iam.PolicyStatement(
                actions=[
                    "elasticache:Connect"
                ],
                effect=_iam.Effect.ALLOW,
                resources=[
                    f"arn:{Aws.PARTITION}:elasticache:{Aws.REGION}:"
                    f"{Aws.ACCOUNT_ID}:serverlesscache:*",
                    f"arn:{Aws.PARTITION}:elasticache:{Aws.REGION}:"
                    f"{Aws.ACCOUNT_ID}:user:*",
                ]
            )
        )
        role.add_to_policy(
            _iam.PolicyStatement(
                actions=[
                    "documentdb:Connect",
                    "documentdb:DescribeDBClusters",
                    "documentdb:Read",
                    "documentdb:Write"
                ],
                effect=_iam.Effect.ALLOW,
                resources=[
                    clusterarn,
                    f"arn:{Aws.PARTITION}:documentdb:{Aws.REGION}:"
                    f"{Aws.ACCOUNT_ID}:dbuser:{resource_id}/{user}",            
                ]
            )
        )
        role.add_to_policy(
            _iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                ],
                resources=[
                    f"arn:aws:s3:::all-purpose-utility/certs/ca-bundle.pem"
                ],
            )

        )
        return role


    def external_secrets_pod_id_role_stmt(self, scope: Construct) -> _iam.Role:
        role = self.get_principal(scope, role_name="ExternalSecretsPodIdentityRole")
        role.add_to_policy(
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
        return role

   
    def model_storage_pod_id_role_stmt(self, scope: Construct, fsx_bucket_arn: str) -> _iam.Role:
        role = self.get_principal(scope, role_name="ModelStoragePodIdentityRole")
        role.add_to_policy(
            _iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:GetBucketLocation",
                ],
                resources=[
                    f"{fsx_bucket_arn}/*",
                    f"{fsx_bucket_arn}",
                ],
            )
        )
        role.add_to_policy(
            _iam.PolicyStatement(
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret"
                ],
                effect=_iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:secretsmanager:{Aws.REGION}:{Aws.ACCOUNT_ID}:secret:hugging-face*"
                ]
            ),
        )
        return role

   
    def vpc_cni_pod_id_role_stmt(self, scope: Construct) -> _iam.Role:
        role = self.get_principal(scope, role_name="VpcCniPodIdentityRole")
        role.add_managed_policy(
            _iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonEKS_CNI_Policy"
            )
        )
        return role


    def ebs_csi_pod_id_role_stmt(self, scope: Construct) -> _iam.Role:
        role = self.get_principal(scope, role_name="EbsCsiPodIdentityRole")
        role.add_managed_policy(
            _iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AmazonEBSCSIDriverPolicy"
            )
        )
        return role


    def karpenter_node_role_stmt(self, scope: Construct, clustername: str) -> _iam.Role:
        policy_statements = RolePolicyStatements()
        role = _iam.Role(
            scope,
            "KarpenterNodeRole",
            role_name=f"KarpenterNodeRole-{clustername}",
            assumed_by=_iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=policy_statements.karp_node_statement(),
        )
        return role

        
    def karpenter_ctrl_pod_id_role_stmt(
        self,
        scope: Construct, 
        cluster_name: str,
        cluster_arn: str, 
        queue_arn: str,
        system_node_group_role_arn: str
    ) -> _iam.Role:

        policy_statements = RolePolicyStatements()
        role = _iam.Role(
            scope,
            "KarpenterPodIdentityRole",
            role_name="KarpenterPodIdentityRole",
            assumed_by=_iam.ServicePrincipal("pods.eks.amazonaws.com")
            .with_session_tags().with_conditions({
                "StringEquals": {
                    "aws:SourceAccount": Aws.ACCOUNT_ID,
                    "aws:SourceArn": (
                        f"arn:{Aws.PARTITION}:eks:{Aws.REGION}:{Aws.ACCOUNT_ID}:cluster/{cluster_name}"
                    ),
                }
            }),
        )
        role.attach_inline_policy(
            _iam.Policy(scope, "KarpenterControllerPolicy",
                policy_name="KarpenterControllerPolicy",
                statements=policy_statements.karp_controller_statement(
                    scope=scope,
                    clustername=cluster_name, 
                    clusterarn=cluster_arn, 
                    queuearn=queue_arn, 
                    region=f"{Aws.REGION}",
                    system_node_group_role_arn=system_node_group_role_arn
                )
            )
        )
        return role


    def spark_pod_id_role_stmt(self, scope: Construct, bucket_arn: str) -> _iam.Role:
        role = self.get_principal(scope, role_name="SparkPodIdentityRole")
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


    def ecomm_pod_id_role_stmt(self, scope: Construct):
        policy_statements = RolePolicyStatements()
        role = self.get_principal(scope, role_name="EcommPodIdentityRole")
        role.attach_inline_policy(
            _iam.Policy(scope, "EcommAppPolicy",
                policy_name="EcommAppPolicy",
                statements=policy_statements.ecomm_pod_statement()
            )
        )
        return role


    def alb_pod_id_role_stmt(self, scope: Construct) -> _iam.Role:
        policy_statements = RolePolicyStatements()
        role = self.get_principal(scope, role_name="AlbPodIdentityRole")
        role.attach_inline_policy(
            _iam.Policy(scope, "AlbPolicy",
                policy_name="AlbPolicy",
                statements=policy_statements.alb_loadbalancer_statement()
            )
        )   
        return role


    def fsx_csi_controller_role_stmt(self, scope: Construct) -> _iam.Role:
        role = self.get_principal(scope, role_name="FsxCsiControllerRole")
        role.add_managed_policy(
            _iam.ManagedPolicy.from_aws_managed_policy_name("AmazonFSxFullAccess")
        )
        return role
