from aws_cdk import (
    Duration,
    aws_lambda as _lambda,
    aws_iam as _iam,
    custom_resources as cr,
    CustomResource,
    RemovalPolicy
)
from constructs import Construct
from dataclasses import dataclass


@dataclass
class ProfileProps:
    """Optional: Define a class or typed dict to handle input configurations cleanly."""   
    role_name: str

class InstanceProfileCleanup(Construct):
    def __init__(self, scope: Construct, id: str, props: ProfileProps, **kwargs) -> None:
        super().__init__(scope, id,**kwargs)


        instance_profile_cleanup_lambda = _lambda.Function(
            self,
            "KarpenterNodeRoleCleanupLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            timeout=Duration.minutes(2),
            environment={
                "ROLE_NAME": props.role_name
            },
            code=_lambda.Code.from_inline(
                """
import os
import boto3

iam_client = boto3.client("iam")

def handler(event, context):

    request_type = event.get("RequestType")
    role_name = os.environ["ROLE_NAME"]

    if request_type == "Delete":
    
        print(f"Listing instance profiles for role {role_name}")

        paginator = iam_client.get_paginator('list_instance_profiles_for_role')
        for page in paginator.paginate(RoleName=role_name):
            for profile in page['InstanceProfiles']:
                profile_name = profile['InstanceProfileName']
                print(f"Removing role {role_name} from instance profile {profile_name}")
                
                iam_client.remove_role_from_instance_profile(
                    InstanceProfileName=profile_name,
                    RoleName=role_name
                )
                print(f"Deleting instance profile {profile_name}")
                iam_client.delete_instance_profile(
                    InstanceProfileName=profile_name
                )
    return {"PhysicalResourceId": f"IamCleanup-{role_name}"}   
                """
            ),
        )

        instance_profile_cleanup_lambda.add_to_role_policy(
            _iam.PolicyStatement(
                actions=[
                    "iam:RemoveRoleFromInstanceProfile",
                    "iam:DeleteInstanceProfile",
                    "iam:ListInstanceProfilesForRole"
                ],
                resources=[
                    "*"
                ]
            )
        )
        provider = cr.Provider(
            self,
            "KarpenterNodeRoleCleanupProvider",
            on_event_handler=instance_profile_cleanup_lambda
        )

        CustomResource(
            self,
            "KarpenterNodeRoleCleanup",
            service_token=provider.service_token,
            removal_policy=RemovalPolicy.DESTROY
        )