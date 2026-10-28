from aws_cdk import (
    aws_ec2 as ec2,
    aws_eks as eks,
    aws_iam as _iam,
    aws_s3 as s3,
    Stack,
    aws_fsx as fsx,    
    RemovalPolicy
)
from constructs import Construct

from configs.roles import RoleStatements

   
class LustreStack(Stack):

    def __init__(
            self, 
            scope: Construct, 
            construct_id: str,
            vpc: ec2.IVpc, 
            **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)


        self.data_bucket = s3.Bucket(
            self,
            "DataBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        
        # Create a security Group for FSx Lustre
        self.fsx_security_group = ec2.SecurityGroup(
            self, "FSxLustreSecurityGroup",
            vpc=vpc,
            description="Security group for FSx Lustre",
            security_group_name="fsx-lustre-sg"
        )

       
        self.model_file_system = fsx.LustreFileSystem(
            self, "ModelFsxLustreFileSystem",
            vpc=vpc,
            vpc_subnet=vpc.private_subnets[0],
            storage_capacity_gib=1200,
            file_system_type_version=fsx.FileSystemTypeVersion.V_2_15,
            security_group=self.fsx_security_group,
            # Configuration settings for Lustre
            lustre_configuration=fsx.LustreConfiguration(
                deployment_type=fsx.LustreDeploymentType.PERSISTENT_2,
                per_unit_storage_throughput=125,
                data_compression_type=fsx.LustreDataCompressionType.LZ4,
            ),
            removal_policy=RemovalPolicy.DESTROY
        )

        fsx.CfnDataRepositoryAssociation(
            self, "DataRepositoryAssociation",
            file_system_id=self.model_file_system.file_system_id,
            file_system_path="/models",
            data_repository_path=f"s3://{self.data_bucket.bucket_name}/models",
            s3=fsx.CfnDataRepositoryAssociation.S3Property(
                auto_import_policy=fsx.CfnDataRepositoryAssociation.AutoImportPolicyProperty(
                    events=["NEW", "CHANGED", "DELETED"]
                ),
                auto_export_policy=fsx.CfnDataRepositoryAssociation.AutoExportPolicyProperty(
                    events=["NEW", "CHANGED", "DELETED"]
                )
            )
        )


        

    @property
    def luster_info(self) -> dict:
        return {
            "fsx-id": self.model_file_system.file_system_id, 
            "fsx-dns-name": self.model_file_system.dns_name,
            "fsx-mount-name": self.model_file_system.mount_name,
            "fsx-bucket-arn": self.data_bucket.bucket_arn,
            "fsx-bucket-name": self.data_bucket.bucket_name
        }














        


   
