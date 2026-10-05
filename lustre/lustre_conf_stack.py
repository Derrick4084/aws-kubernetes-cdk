import yaml
from aws_cdk import (
    aws_ec2 as ec2,
    aws_iam as _iam,
    aws_s3 as s3,
    Stack,
    aws_eks as eks,
    aws_fsx as fsx,    
)
from constructs import Construct

   
class LustreConfigStack(Stack):

    def __init__(self, scope: Construct, construct_id: str,
            cluster: eks.Cluster,
            fsx_security_group: ec2.ISecurityGroup,
            **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        
        ec2.CfnSecurityGroupIngress(
            self,
            "FsxLustreIngressRule",
            group_id=fsx_security_group.security_group_id,
            source_security_group_id=cluster.cluster_security_group_id,
            ip_protocol="tcp",
            from_port=988,
            to_port=1023,
            description="Allow Lustre traffic within VPC"
        )

        fsx_csi_controller_role = _iam.Role(
            self,
            "FsxCsiControllerRole",
            assumed_by=_iam.ServicePrincipal("pods.eks.amazonaws.com").with_session_tags(),
            description="IAM role for the AWS FSx CSI controller",
            managed_policies=[
                _iam.ManagedPolicy.from_aws_managed_policy_name("AmazonFSxFullAccess")
            ]
        )
                     
        eks.CfnAddon(
            self,
            "fsx-csi-driver-addon",
            addon_name = "aws-fsx-csi-driver",
            pod_identity_associations=[
                eks.CfnAddon.PodIdentityAssociationProperty(
                    role_arn=fsx_csi_controller_role.role_arn,
                    service_account="fsx-csi-controller-sa"
                )
            ],
            namespace_config=eks.CfnAddon.NamespaceConfigProperty(
                namespace="kube-system"
            ),
            cluster_name = cluster.cluster_name,
            addon_version = "v1.10.0-eksbuild.2",
            resolve_conflicts="OVERWRITE"
        )
        

       
        
        

        