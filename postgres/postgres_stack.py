from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_ec2 as ec2,
    CfnOutput,
    aws_rds as rds,
    aws_lambda as lambda_,
    Duration,
    CustomResource
)
from constructs import Construct


class PostgresDBStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, 
                 vpc: ec2.Vpc, 
                 **kwargs
                ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        
        self.vpc = vpc

        # Create a Security Group for the PostgreSQL Database
        self.postgres_sg = ec2.SecurityGroup(self, "PostgresSG", 
            vpc=self.vpc,
            description="Security group for PostgreSQL database",
            security_group_name="PostgresDBSG"
        )
        
        # Add Ingress Rule to allow connections to the PostgreSQL Database from anywhere
        # TODO: Restrict this to specific IP ranges or VPC CIDR blocks
        # WARNING: This is not recommended for production environments
        self.postgres_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(5432),
            description="Allow PostgreSQL access from anywhere"
        )

        # Create an Aurora PostgreSQL Cluster
        self.postgres_db_cluster = rds.DatabaseCluster(self, "PostgresDBCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(version=rds.AuroraPostgresEngineVersion.VER_17_6),
            writer=rds.ClusterInstance.serverless_v2("writer"),
            serverless_v2_min_capacity=0.5,
            serverless_v2_max_capacity=2,
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[self.postgres_sg],
            default_database_name="monolithservices",
            removal_policy=RemovalPolicy.DESTROY,
            cluster_identifier="postgres-cluster",
            credentials=rds.Credentials.from_generated_secret("postgres"),
            storage_encrypted=True,
            enable_data_api=True
        )



        db_creator_lambda = lambda_.Function(self, "DBCreatorLambda",
            runtime=lambda_.Runtime.PYTHON_3_12,
            function_name="postgres-db-creator",
            handler="index.handler",
            code=lambda_.Code.from_inline('''
import json
import boto3
import psycopg2
import cfnresponse
from psycopg2 import sql


def handler(event, context):
    try:
        if event['RequestType'] == 'Delete':
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
            return
        
        secret_arn = event['ResourceProperties']['SecretArn']
        databases = event['ResourceProperties']['Databases']
        schemas = event['ResourceProperties']['Schemas']
        
        sm = boto3.client('secretsmanager')
        secret = json.loads(sm.get_secret_value(SecretId=secret_arn)['SecretString'])
        
        admin_conn = psycopg2.connect(
            host=secret['host'],
            port=secret['port'],
            user=secret['username'],
            password=secret['password'],
            database='postgres'
        )
        admin_conn.autocommit = True
        admin_cursor = admin_conn.cursor()
        
        for db in databases:
            admin_cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,))
            exists = admin_cursor.fetchone()

            if not exists:
                admin_cursor.execute(
                    sql.SQL("CREATE DATABASE {}")
                    .format(sql.Identifier(db))
                )
                print(f"Created database: {db}")
            else:
                print(f"Database already exists: {db}")

            if db == 'ecomm':
                db_conn = psycopg2.connect(
                    host=secret['host'],
                    port=secret['port'],
                    user=secret['username'],
                    password=secret['password'],
                    database=db
                )
                db_conn.autocommit = True
                db_cursor = db_conn.cursor()

                # Create application schemas
                for schema in schemas:
                    db_cursor.execute(
                        sql.SQL("CREATE SCHEMA IF NOT EXISTS {}")
                        .format(sql.Identifier(schema))
                    )
                db_cursor.close()
                                          
            db_conn.close()
        admin_cursor.close()
        admin_conn.close() 
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
                                          
    except Exception as e:
        print(f"Error: {str(e)}")
        cfnresponse.send(
            event,
            context,
            cfnresponse.FAILED,
            {"Message": str(e)}
        )
'''),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[self.postgres_sg],
            timeout=Duration.minutes(5),
            layers=[
                lambda_.LayerVersion(
                    self, "Psycopg2Layer",
                    code=lambda_.Code.from_asset("lambda/psycopg2"),
                    compatible_runtimes=[lambda_.Runtime.PYTHON_3_12]
                )
            ]
        )
        db_creator_lambda.node.add_dependency(self.postgres_db_cluster)


        self.postgres_db_cluster.secret.grant_read(db_creator_lambda)


        # Custom resource to trigger database and schema creation
        CustomResource(self, "DatabaseCreator",
            service_token=db_creator_lambda.function_arn,
            properties={
                "SecretArn": self.postgres_db_cluster.secret.secret_arn,
                "Databases": ["ecomm"],
                "Schemas": ["ordering", "payment", "platform", "product", "rag", "security", "shipping", "web"]
            }
        )
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        CfnOutput(self, "ClusterEndpoint", value=self.postgres_db_cluster.cluster_endpoint.hostname)
        CfnOutput(self, "SecretName", value=self.postgres_db_cluster.secret.secret_name)


    @property
    def postgres_info(self) -> dict:
        return {
            "secret-name": self.postgres_db_cluster.secret.secret_name,
            "security-group-id": self.postgres_sg.security_group_id
        }