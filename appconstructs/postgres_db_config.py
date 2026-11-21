from aws_cdk import (
    Duration,
    aws_lambda as _lambda,
    aws_ec2 as ec2,
    aws_iam as _iam,
    custom_resources as cr,
    CustomResource,
    RemovalPolicy
)
from constructs import Construct
from dataclasses import dataclass


@dataclass
class PgDbProps:
    """Optional: Define a class or typed dict to handle input configurations cleanly."""   
    secret_arn: str
    vpc: ec2.IVpc
    postgres_sg: ec2.ISecurityGroup

class PostgresDbConfig(Construct):
    def __init__(self, scope: Construct, id: str, props: PgDbProps, **kwargs) -> None:
        super().__init__(scope, id,**kwargs)


        self.db_creator_lambda = _lambda.Function(self, "DBCreatorLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            function_name="postgres-db-creator",
            handler="index.handler",
            code=_lambda.Code.from_inline('''
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
            vpc=props.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[props.postgres_sg],
            timeout=Duration.minutes(5),
            layers=[
                _lambda.LayerVersion(
                    self, "Psycopg2Layer",
                    code=_lambda.Code.from_asset("lambda/psycopg2"),
                    compatible_runtimes=[_lambda.Runtime.PYTHON_3_12]
                )
            ]
        )


        # Custom resource to trigger database and schema creation
        CustomResource(self, "DatabaseCreator",
            service_token=self.db_creator_lambda.function_arn,
            properties={
                "SecretArn": props.secret_arn,
                "Databases": ["ecomm"],
                "Schemas": ["ordering", "payment", "platform", "product", "rag", "security", "shipping", "web"]
            }
        )