from aws_cdk import (
    aws_lambda as _lambda,
    aws_iam as _iam,
    custom_resources as cr,
    Fn
)
from constructs import Construct
from dataclasses import dataclass


@dataclass
class DbProps:
    """Optional: Define a class or typed dict to handle input configurations cleanly."""   
    secret_arn: str
    db_endpoint: str

class DocumentDbSecretUpdate(Construct):
    def __init__(self, scope: Construct, id: str, props: DbProps, **kwargs) -> None:
        super().__init__(scope, id,**kwargs)


        """
        Here we need to use a custom resource to update the secret with the endpoints
        of the DocumentDB clusters. This is because the endpoints are not available
        until the clusters are created, and we need to pass them to other stacks.
        
        """
        # Lambda function to update the secret with the DocumentDB endpoints
        update_lambda = _lambda.Function(self, "UpdateSecretLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            function_name="documentdb-update-secret",
            code=_lambda.Code.from_inline("""
import json
import boto3
                                            
def handler(event, context):
    if event['RequestType'] in ['Create', 'Update']:
        client = boto3.client('secretsmanager')
        secret = json.loads(client.get_secret_value(SecretId=event['ResourceProperties']['SecretArn'])['SecretString'])
        secret['documentdb_endpoint'] = event['ResourceProperties']['DocumentDbEndpoint']                                     
        client.put_secret_value(SecretId=event['ResourceProperties']['SecretArn'], SecretString=json.dumps(secret))
    return {'PhysicalResourceId': 'UpdateSecretWithEndpoints'}
""")
)
        update_lambda.add_to_role_policy(_iam.PolicyStatement(
            actions=[
                "secretsmanager:GetSecretValue",
                "secretsmanager:PutSecretValue"
            ],
            resources=[props.secret_arn]
        ))

        # Custom resource to update the secret with the DocumentDB endpoints
        cr.AwsCustomResource(self, "UpdateSecretWithEndpoints",
            on_create=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={
                    "FunctionName": update_lambda.function_name,
                    "Payload": Fn.join("", [
                        '{"RequestType":"Create","ResourceProperties":{"SecretArn":"', props.secret_arn,
                        '","DocumentDbEndpoint":"', props.db_endpoint, '"}}'
                    ])
                },
                physical_resource_id=cr.PhysicalResourceId.of("UpdateSecretWithEndpoints")
            ),
            on_update=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={
                    "FunctionName": update_lambda.function_name,
                    "Payload": Fn.join("", [
                        '{"RequestType":"Update","ResourceProperties":{"SecretArn":"', props.secret_arn,
                        '","DocumentDbEndpoint":"', props.db_endpoint, '"}}'
                    ])
                },
                physical_resource_id=cr.PhysicalResourceId.of("UpdateSecretWithEndpoints")
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements([
                _iam.PolicyStatement(
                    actions=["lambda:InvokeFunction"],
                    resources=[update_lambda.function_arn]
                )
            ])
        )