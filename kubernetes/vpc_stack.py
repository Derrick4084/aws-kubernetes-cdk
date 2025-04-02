from aws_cdk import (
    Aws,
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

class VpcStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)


        self.vpcflowlogrole = _iam.Role(self, "vpcflowlogsrole",
                assumed_by=_iam.ServicePrincipal("vpc-flow-logs.amazonaws.com"),
                path="/"
        )
        self.vpcflowlogrole.attach_inline_policy(
            _iam.Policy(
                self, 
                "vpcflowlogspolicy",
                policy_name="VpcFlowLogsPolicy",
                statements=[_iam.PolicyStatement(
                    effect=_iam.Effect.ALLOW,
                    actions=["logs:CreateLogGroup", 
                             "logs:CreateLogStream", 
                             "logs:PutLogEvents",
                             "logs:DescribeLogGroups",
                             "logs:DescribeLogStreams",
                             "logs:DeleteLogGroup",
                             "logs:DeleteLogStream"
                            ],
                    resources=[f"arn:aws:logs:{Aws.ACCOUNT_ID}:{Aws.REGION}:log-group:/VPCforEKS/vpcflowlogs*"]
                   )
                ]
            )
        )

        # create a log group for vpc flow logs
        self.vpcflowloggroup = logs.LogGroup(
            self, 
            "vpcflowloggroup",
            log_group_name=f"/VPCforEKS/vpcflowlogs",
            retention= logs.RetentionDays.ONE_DAY,
            removal_policy=RemovalPolicy.DESTROY
        )

        # create a flow log bucket
        self.log_bucket = s3.Bucket(
            self,
            "vpcflowlogsbucket",
            bucket_name=f"vpcflowlogs-{Aws.ACCOUNT_ID}",
            removal_policy=RemovalPolicy.DESTROY,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            auto_delete_objects=True,
            versioned=True,
        )

        # create a vpc
        self.vpc = ec2.Vpc(self, "BaseVpc",
          ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
          availability_zones=[f"{Aws.REGION}a", f"{Aws.REGION}b"],
          create_internet_gateway=True,
          enable_dns_hostnames=True,
          enable_dns_support=True,
          vpc_name="VPCforEKS",
          subnet_configuration=[
            ec2.SubnetConfiguration(
               cidr_mask=24,
               name='public1',
               subnet_type=ec2.SubnetType.PUBLIC,
              ),
            ec2.SubnetConfiguration(
               cidr_mask=24,
               name='private1',
               subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
              )],
          gateway_endpoints={
            "S3": ec2.GatewayVpcEndpointOptions(
                service=ec2.GatewayVpcEndpointAwsService.S3
            ),
            "DynamoDB": ec2.GatewayVpcEndpointOptions(
                service=ec2.GatewayVpcEndpointAwsService.DYNAMODB
            )
          }
        )
        Tags.of(self.vpc.private_subnets[0]).add("kubernetes.io/role/internal-elb", "1")
        Tags.of(self.vpc.private_subnets[1]).add("kubernetes.io/role/internal-elb", "1")

        # create vpc flow logs for cloudwatch
        self.ec2_vpc_to_cloudwatch_flowlog = ec2.FlowLog(self, "cloudwatch-FlowLog",
          traffic_type=ec2.FlowLogTrafficType.ALL,
          flow_log_name="vpc-cw-flowlogs",                                        
          resource_type=ec2.FlowLogResourceType.from_vpc(self.vpc),
          destination=ec2.FlowLogDestination.to_cloud_watch_logs(self.vpcflowloggroup, self.vpcflowlogrole)
         )
        
        # create vpc flow logs for s3
        self.ec2_vpc_to_s3_flowlog = ec2.FlowLog(self, "s3-FlowLog",
          traffic_type=ec2.FlowLogTrafficType.ALL,
          flow_log_name="vpc-s3-flowlogs",                           
          resource_type=ec2.FlowLogResourceType.from_vpc(self.vpc),
          destination=ec2.FlowLogDestination.to_s3(
                      bucket=self.log_bucket,
                      key_prefix="vpcflowlogs"
                )        
        )

        eks_cluster_sg = ec2.SecurityGroup(
            self, "EKSClusterSG",
            vpc=self.vpc,
            allow_all_outbound=True,
            security_group_name="eks_cluster-sg"    
        )
        eks_cluster_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.all_traffic())
        
        # Endpoints for private subnet with no NAT Gateway
        # vpc_interface_endpoints = {         
        #     "ec2": ec2.InterfaceVpcEndpointAwsService.EC2,
        #     "ec2-messages": ec2.InterfaceVpcEndpointAwsService.EC2_MESSAGES,
        #     "ssm": ec2.InterfaceVpcEndpointAwsService.SSM,
        #     "ssm-messages": ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
        #     "cloudformation": ec2.InterfaceVpcEndpointAwsService.CLOUDFORMATION,
        #     "cloudwatch-logs": ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
        #     "cloudwatch-monitoring": ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_MONITORING,
        #     "sts": ec2.InterfaceVpcEndpointAwsService.STS,
        #     "ecr-api": ec2.InterfaceVpcEndpointAwsService.ECR,
        #     "ecr-dkr": ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
        #     "load-balancing": ec2.InterfaceVpcEndpointAwsService.ELASTIC_LOAD_BALANCING,
        # }

        # for name, interface_service in vpc_interface_endpoints.items():
        #     self.vpc.add_interface_endpoint(f"{name}",
        #      service=interface_service,
        #      private_dns_enabled=True,
        #      subnets=ec2.SubnetSelection(subnets=self.vpc.private_subnets)
        #   )

        CfnOutput(self, "VPC ID", value=self.vpc.vpc_id, export_name="VPCID")
        CfnOutput(self, "EKS SEC GROUP", value=eks_cluster_sg.security_group_id, export_name="EKSSecurityGroupID")
        CfnOutput(self, "PrivateSubnet1", value=self.vpc.private_subnets[0].subnet_id, export_name="PrivateSubnet1")
        CfnOutput(self, "PrivateSubnet2", value=self.vpc.private_subnets[1].subnet_id, export_name="PrivateSubnet2")
        CfnOutput(self, "PrivateSubnetRouteTableID1", value=self.vpc.private_subnets[0].route_table.route_table_id, export_name="PrivateSubnetRouteTableID1")
        CfnOutput(self, "PrivateSubnetRouteTableID2", value=self.vpc.private_subnets[1].route_table.route_table_id, export_name="PrivateSubnetRouteTableID2")