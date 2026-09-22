from aws_cdk import (
    aws_ec2 as ec2,
    aws_s3 as s3,
    Stack,
    aws_fsx as fsx,    
    RemovalPolicy
)
from constructs import Construct

from huggingface_hub import hf_hub_download
   
class LustreStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, vpc: ec2.IVpc, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)


        self.data_bucket = s3.Bucket(
            self,
            "DataBucket",
            bucket_name="fsx-lustre-bucket",
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
            security_group=self.fsx_security_group,
            # Configuration settings for Lustre
            lustre_configuration=fsx.LustreConfiguration(
                deployment_type=fsx.LustreDeploymentType.PERSISTENT_2,
                per_unit_storage_throughput=125,
                data_compression_type=fsx.LustreDataCompressionType.LZ4,
                
                # Import/Export integration with S3
                import_path=f"{self.data_bucket.s3_url_for_object()}/models",
                export_path=f"{self.data_bucket.s3_url_for_object()}/export/models"
            )
        )














        


   
