from aws_cdk import (
    aws_iam as _iam,  
    CfnJson,
)


class RolePolicyStatements:
    
    def __init__(self):
        pass
    
    @staticmethod
    def alb_loadbalancer_statement():
        policy_stmnt = [
                    _iam.PolicyStatement(
                    actions=["iam:CreateServiceLinkedRole"],
                    effect=_iam.Effect.ALLOW,
                    resources=["*"],
                    conditions={
                        "StringEquals": {
                            "iam:AWSServiceName": "elasticloadbalancing.amazonaws.com"
                            }
                    },
                    sid="CreateServiceLinkedRoleForElasticLoadBalancing"
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:DescribeAccountAttributes",
                                 "ec2:DescribeAddresses",
                                 "ec2:DescribeAvailabilityZones",
                                 "ec2:DescribeInternetGateways",
                                 "ec2:DescribeVpcs",
                                 "ec2:DescribeVpcPeeringConnections",
                                 "ec2:DescribeSubnets",
                                 "ec2:DescribeSecurityGroups",
                                 "ec2:DescribeInstances",
                                 "ec2:DescribeNetworkInterfaces",
                                 "ec2:DescribeTags",
                                 "ec2:GetCore",
                                 "ec2:DescribeLaunchTemplates",
                                 "ec2:DescribeKeyPairs",
                                 "elasticloadbalancing:DescribeLoadBalancers",
                                 "elasticloadbalancing:DescribeLoadBalancerAttributes",
                                 "elasticloadbalancing:DescribeListeners",
                                 "elasticloadbalancing:DescribeListenerCertificates",
                                 "elasticloadbalancing:DescribeSSLPolicies",
                                 "elasticloadbalancing:DescribeRules",
                                 "elasticloadbalancing:DescribeTargetGroups",
                                 "elasticloadbalancing:DescribeTargetGroupAttributes",
                                 "elasticloadbalancing:DescribeTargetHealth",
                                 "elasticloadbalancing:DescribeTags"
                                 ],
                        effect=_iam.Effect.ALLOW,
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["cognito-idp:DescribeUserPoolClient",
                                 "acm:ListCertificates",
                                 "acm:DescribeCertificate",
                                 "iam:ListServerCertificates",
                                 "iam:GetServerCertificate",
                                 "waf-regional:GetWebACL",
                                 "waf-regional:GetWebACLForResource",
                                 "waf-regional:AssociateWebACL",
                                 "waf-regional:DisassociateWebACL",
                                 "wafv2:GetWebACL",
                                 "wafv2:GetWebACLForResource",
                                 "wafv2:AssociateWebACL",
                                 "wafv2:DisassociateWebACL",
                                 "shield:GetSubscriptionState",
                                 "shield:DescribeProtection",
                                 "shield:CreateProtection",
                                 "shield:DeleteProtection"
                                 ],
                        effect=_iam.Effect.ALLOW,
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:AuthorizeSecurityGroupIngress",
                                 "ec2:RevokeSecurityGroupIngress"
                                 ],
                        effect=_iam.Effect.ALLOW,
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:CreateSecurityGroup"],
                        effect=_iam.Effect.ALLOW,
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:CreateTags"],
                        effect=_iam.Effect.ALLOW,
                        resources=["arn:aws:ec2:*:*:security-group/*"],
                        conditions={
                            "StringEquals": {
                                "ec2:CreateAction": "CreateSecurityGroup"
                                },
                            "Null": {
                                "aws:RequestTag/elbv2.k8s.aws/cluster": "false"
                           }
                        }
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:CreateTags",
                                 "ec2:DeleteTags"],
                        effect=_iam.Effect.ALLOW,
                        resources=["arn:aws:ec2:*:*:security-group/*"],
                        conditions={
                            "Null": {
                                "aws:RequestTag/elbv2.k8s.aws/cluster": "true",
                                "aws:ResourceTag/elbv2.k8s.aws/cluster": "false"
                                }
                        }
                    ),
                    _iam.PolicyStatement(
                        actions=["ec2:AuthorizeSecurityGroupIngress",
                                 "ec2:RevokeSecurityGroupIngress",
                                 "ec2:DeleteSecurityGroup"
                                 ],
                        resources=["*"],
                        effect=_iam.Effect.ALLOW,
                        conditions={
                            "Null": {
                                "aws:ResourceTag/elbv2.k8s.aws/cluster": "false"
                                }
                        }
                    ),
                    _iam.PolicyStatement(
                        actions=["elasticloadbalancing:CreateLoadBalancer",
                                 "elasticloadbalancing:CreateTargetGroup"
                                 ],
                        effect=_iam.Effect.ALLOW,
                        resources=["*"],
                        conditions={
                            "Null": {
                                "aws:RequestTag/elbv2.k8s.aws/cluster": "false"
                                }
                        }
                    ),
                    _iam.PolicyStatement(
                        actions=["elasticloadbalancing:CreateListener",
                                 "elasticloadbalancing:DeleteListener",
                                 "elasticloadbalancing:CreateRule",
                                 "elasticloadbalancing:DeleteRule"
                                 ],
                        effect=_iam.Effect.ALLOW,
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["elasticloadbalancing:AddTags",
                                 "elasticloadbalancing:RemoveTags"
                                 ],
                        effect=_iam.Effect.ALLOW,
                        resources=[
                            "arn:aws:elasticloadbalancing:*:*:targetgroup/*/*",
                            "arn:aws:elasticloadbalancing:*:*:loadbalancer/net/*/*",
                            "arn:aws:elasticloadbalancing:*:*:loadbalancer/app/*/*"
                            ],
                        conditions={
                            "Null": {
                                "aws:RequestTag/elbv2.k8s.aws/cluster": "true",
                                "aws:ResourceTag/elbv2.k8s.aws/cluster": "false"
                                }
                        }
                    ),
                    _iam.PolicyStatement(
                        actions=["elasticloadbalancing:AddTags",
                                 "elasticloadbalancing:RemoveTags"
                                 ],
                        effect=_iam.Effect.ALLOW,
                        resources=[
                            "arn:aws:elasticloadbalancing:*:*:listener/net/*/*/*",
                            "arn:aws:elasticloadbalancing:*:*:listener/app/*/*/*",
                            "arn:aws:elasticloadbalancing:*:*:listener-rule/net/*/*/*",
                            "arn:aws:elasticloadbalancing:*:*:listener-rule/app/*/*/*"
                            ],
                    ),
                    _iam.PolicyStatement(
                        actions=["elasticloadbalancing:ModifyLoadBalancerAttributes",
                                 "elasticloadbalancing:SetIpAddressType",
                                 "elasticloadbalancing:SetSecurityGroups",
                                 "elasticloadbalancing:SetSubnets",
                                 "elasticloadbalancing:DeleteLoadBalancer",
                                 "elasticloadbalancing:ModifyTargetGroup",
                                 "elasticloadbalancing:ModifyTargetGroupAttributes",
                                 "elasticloadbalancing:DeleteTargetGroup"
                                 ],
                        effect=_iam.Effect.ALLOW,
                        resources=["*"],
                        conditions={
                            "Null": {
                                "aws:ResourceTag/elbv2.k8s.aws/cluster": "false"
                                }
                        }
                    ),
                    _iam.PolicyStatement(
                        actions=["elasticloadbalancing:AddTags"],
                        effect=_iam.Effect.ALLOW,
                        resources=["arn:aws:elasticloadbalancing:*:*:targetgroup/*/*",
                                   "arn:aws:elasticloadbalancing:*:*:loadbalancer/net/*/*",
                                   "arn:aws:elasticloadbalancing:*:*:loadbalancer/app/*/*"],
                        conditions={
                            "StringEquals": {
                                "elasticloadbalancing:CreateAction": [
                                    "CreateTargetGroup",
                                    "CreateLoadBalancer"
                                    ]
                               },
                                "Null": {
                                "aws:RequestTag/elbv2.k8s.aws/cluster": "false"
                                }  
                             }                                                    
                        ),
                    _iam.PolicyStatement(
                        actions=["elasticloadbalancing:RegisterTargets",
                                 "elasticloadbalancing:DeregisterTargets"
                                 ],
                        effect=_iam.Effect.ALLOW,
                        resources=["arn:aws:elasticloadbalancing:*:*:targetgroup/*/*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["elasticloadbalancing:SetWebAcl",
                                "elasticloadbalancing:ModifyListener",
                                "elasticloadbalancing:AddListenerCertificates",
                                "elasticloadbalancing:RemoveListenerCertificates",
                                "elasticloadbalancing:ModifyRule"
                                ],
                        effect=_iam.Effect.ALLOW,
                        resources=[
                            "arn:aws:elasticloadbalancing:*:*:listener/net/*/*/*",
                            "arn:aws:elasticloadbalancing:*:*:listener/app/*/*/*",
                            "arn:aws:elasticloadbalancing:*:*:listener-rule/net/*/*/*",
                            "arn:aws:elasticloadbalancing:*:*:listener-rule/app/*/*/*"
                        ]
                    ),

                ]      
        return policy_stmnt


    @staticmethod
    def amp_iamproxy_ingest_statement():
        policy_stmnt = [_iam.PolicyStatement(
                    actions=["aps:RemoteWrite", 
                             "aps:GetSeries", 
                             "aps:GetLabels",
                             "aps:GetMetricMetadata"
                            ],
                    effect=_iam.Effect.ALLOW,
                    resources=["*"],
                    sid="ingestpromteheusmetrics"
                    )]
        return policy_stmnt
    
    @staticmethod
    def amp_iamproxy_query_statement():
        policy_stmnt = [_iam.PolicyStatement(
                    actions=["aps:QueryMetrics",
                             "aps:GetSeries", 
                             "aps:GetLabels",
                             "aps:GetMetricMetadata"
                            ],
                    effect=_iam.Effect.ALLOW,
                    resources=["*"],
                    sid="querypromteheusmetrics"
                    )]
        return policy_stmnt
    

    @staticmethod
    def grafana_managed_statement(workspace_arn: str, amp_workspace_arn: str):
        policy_stmnt = [
            _iam.PolicyStatement(
                actions=[
                    "grafana:DescribeWorkspace",
                    "grafana:UpdateWorkspace",
                    "grafana:ListWorkspaces",
                ],
                effect=_iam.Effect.ALLOW,
                resources=[workspace_arn]
            ),
            _iam.PolicyStatement(
                actions=[
                    "aps:ListWorkspaces",
                    "aps:DescribeWorkspace",
                    "aps:QueryMetrics",
                    "aps:GetLabels",
                    "aps:GetSeries",
                    "aps:GetMetricMetadata"
                ],
                effect=_iam.Effect.ALLOW,
                resources=[amp_workspace_arn]
            ),
        ]
        return policy_stmnt

    
    @staticmethod
    def grafana_inline_statement(acc_id):
        policy_stmnt = [
                    _iam.PolicyStatement(
                        actions=[
                            "aps:ListWorkspaces",
                            "aps:DescribeWorkspace",
                            "aps:QueryMetrics",
                            "aps:GetLabels",
                            "aps:GetSeries",
                            "aps:GetMetricMetadata"
                            ],
                        effect=_iam.Effect.ALLOW,
                        resources=["*"]
                    ),
                    _iam.PolicyStatement(
                        actions=["sns:Publish"],
                        effect=_iam.Effect.ALLOW,
                        resources=[f"arn:aws:sns:*:{acc_id}:grafana*"]
                    ),
              ]               
        return policy_stmnt


    
    @staticmethod
    def eks_cluster_statement():
        policy_stmnt = [
            _iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKSClusterPolicy")
        ]               
        return policy_stmnt

    
    @staticmethod
    def karp_node_statement():
        policy_stmnt = [
                  _iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKSWorkerNodePolicy"),
                  _iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKS_CNI_Policy"),
                  _iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryReadOnly"),
                  _iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
              ]               
        return policy_stmnt

    @staticmethod
    def karp_controller_statement(scope, clustername: str, clusterarn: str, rolearn: str, queuearn: str, region: str):
        policy_stmnt = [
            _iam.PolicyStatement(
                    sid="KarpenterEC2Launch",
                    effect=_iam.Effect.ALLOW,
                    actions=[
                        "ec2:RunInstances",
                        "ec2:CreateLaunchTemplate",
                        "ec2:DeleteLaunchTemplate",
                        "ec2:CreateFleet"
                    ],
                    resources=["*"],
                    
                ),
            _iam.PolicyStatement(
                sid="KarpenterResourceDiscovery",
                effect=_iam.Effect.ALLOW,
                actions=[
                        "ssm:GetParameter",
                        "ec2:DescribeImages",             
                        "ec2:DescribeSubnets",
                        "ec2:DescribeSecurityGroups",
                        "ec2:DescribeLaunchTemplates",
                        "ec2:DescribeInstances",
                        "ec2:DescribeInstanceTypes",
                        "ec2:DescribeInstanceTypeOfferings",
                        "ec2:DescribeCapacityReservations",
                        "ec2:DescribeAvailabilityZones",                           
                        "ec2:DescribeSpotPriceHistory",
                        "pricing:GetProducts"
                    ],
                resources=["*"],       
            ),                 
            _iam.PolicyStatement(
                sid="ConditionalEC2Termination",
                effect=_iam.Effect.ALLOW,
                actions=["ec2:TerminateInstances"],
                resources=["*"],
                conditions={"StringLike": {"ec2:ResourceTag/karpenter.sh/nodepool": "*"}}
            ),
            _iam.PolicyStatement(
                sid="AllowPassingInstanceRole",
                effect=_iam.Effect.ALLOW,
                actions=["iam:PassRole"],
                resources=[rolearn],
                conditions={
                        "StringEquals": {
                            "iam:PassedToService": "ec2.amazonaws.com"
                        }
                    },
                    
            ),            
            _iam.PolicyStatement(
                sid="EKSClusterEndpointLookup",
                effect=_iam.Effect.ALLOW,
                actions=["eks:DescribeCluster"],
                resources=[clusterarn]
            ),
            _iam.PolicyStatement(
                sid="AllowScopedInstanceProfileCreationActions",
                effect=_iam.Effect.ALLOW,
                actions=["iam:CreateInstanceProfile"],
                resources=["*"],
                conditions={
                    "StringEquals": CfnJson(scope, "KarpenterCreateInstanceProfileCondition",
                    value={
                        f"aws:RequestTag/kubernetes.io/cluster/{clustername}": "owned",
                        "aws:RequestTag/topology.kubernetes.io/region": region
                    }
                ),
                "StringLike": {
                    "aws:RequestTag/karpenter.k8s.aws/ec2nodeclass": "*"
                },
                    }
            ),
            _iam.PolicyStatement(
                sid="AllowScopedInstanceProfileTagActions",
                effect=_iam.Effect.ALLOW,
                actions=["iam:TagInstanceProfile"],
                resources=["*"],
                conditions={
                    "StringEquals": CfnJson(scope, "KarpenterTagInstanceProfileCondition",
                        value={
                            f"aws:ResourceTag/kubernetes.io/cluster/{clustername}": "owned",
                            "aws:ResourceTag/topology.kubernetes.io/region": region,
                            f"aws:RequestTag/kubernetes.io/cluster/{clustername}": "owned",
                            "aws:RequestTag/topology.kubernetes.io/region": region
                        }
                    ),
                    "StringLike": {
                        "aws:ResourceTag/karpenter.k8s.aws/ec2nodeclass": "*",
                        "aws:RequestTag/karpenter.k8s.aws/ec2nodeclass": "*"
                    },
                }
            ),                   
            _iam.PolicyStatement(
                sid="AllowScopedInstanceProfileActions",
                effect=_iam.Effect.ALLOW,
                actions=["iam:AddRoleToInstanceProfile",
                        "iam:RemoveRoleFromInstanceProfile",
                        "iam:DeleteInstanceProfile"],
                resources=["*"],
                conditions={
                    "StringEquals": CfnJson(scope, "KarpenterInstanceProfileActionsCondition",
                        value={
                            f"aws:ResourceTag/kubernetes.io/cluster/{clustername}": "owned",
                            "aws:ResourceTag/topology.kubernetes.io/region": region
                        }
                    ),
                    "StringLike": {
                        "aws:ResourceTag/karpenter.k8s.aws/ec2nodeclass": "*"
                    },
                }
            ),
            _iam.PolicyStatement(
                sid="AllowInstanceProfileReadActions",
                effect=_iam.Effect.ALLOW,
                actions=[
                    "iam:GetInstanceProfile",
                    "iam:ListInstanceProfiles"
                ],
                resources=["*"]
            ),
            _iam.PolicyStatement(
                sid="KarpenterInterruptionQueue",
                effect=_iam.Effect.ALLOW,
                actions=["sqs:DeleteMessage",
                         "sqs:ReceiveMessage",
                         "sqs:GetQueueUrl",
                         "sqs:GetQueueAttributes",
                         ],
                resources=[queuearn]
            )          
              ]       
        return policy_stmnt
        
