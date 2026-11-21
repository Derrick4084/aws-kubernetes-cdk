from aws_cdk import (
    Stack,
    aws_docdb as documentdb,
    aws_ec2 as ec2,
    aws_secretsmanager as secretsmanager
)
from constructs import Construct
from appconstructs.documentdb_secret_update import DbProps, DocumentDbSecretUpdate
import json


class DocumentDBStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, vpc: ec2.Vpc, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.vpc = vpc

        # Create a secret to store the DocumentDB credentials
        self.documentdb_master_user = "docadmin"
        self.documentdb_secret = secretsmanager.Secret(self, "DocumentDBSecret",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username":"' + self.documentdb_master_user + '", "port": 27017, "documentdb_endpoint": ""}',
                generate_string_key="password",
                exclude_punctuation=True,
                password_length=12,
                require_each_included_type=True
            ))

        # Subnet group and security group for DocumentDB cluster       
        self.documentdb_subnet_group = documentdb.CfnDBSubnetGroup(self, "DocumentDBSubnetGroup",
            db_subnet_group_name="documentdb-subnet-group",
            subnet_ids=self.vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS).subnet_ids,
            db_subnet_group_description="Subnet group for DocumentDB"
        )
        self.documentdb_security_group = ec2.SecurityGroup(self, "DocumentDBSecurityGroup",
            vpc=self.vpc,
            security_group_name="documentdb-sg",
            description="Security group for DocumentDB"
        )
        self.documentdb_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(27017),
            description="Allow access from private subnets"
        )

    
        self.document_db = documentdb.CfnDBCluster(self, "DocDB",
            engine_version="5.0.0",
            db_cluster_identifier="documentdb-cluster",
            serverless_v2_scaling_configuration=documentdb.CfnDBCluster.ServerlessV2ScalingConfigurationProperty(
                min_capacity=0.5,
                max_capacity=2.0
            ),
            storage_encrypted=True,    
            master_username=self.documentdb_master_user,
            master_user_password=self.documentdb_secret.secret_value_from_json("password").unsafe_unwrap(),
            vpc_security_group_ids=[self.documentdb_security_group.security_group_id],
            db_subnet_group_name=self.documentdb_subnet_group.db_subnet_group_name,
            port=27017
        )
        self.document_db.add_dependency(self.documentdb_subnet_group)
        self.document_db_instance = documentdb.CfnDBInstance(self, "DocDBInstance",
            db_cluster_identifier=self.document_db.ref,
            db_instance_identifier="instance-1",
            db_instance_class="db.t3.medium"
        )

  
        """
        Here we need to use a custom resource to update the secret with the endpoints
        of the DocumentDB clusters. This is because the endpoints are not available
        until the clusters are created, and we need to pass them to other stacks.
        
        """
        db_props = DbProps(
            secret_arn=self.documentdb_secret.secret_arn,
            db_endpoint=self.document_db.attr_endpoint,
        )
        document_db_secret_update = DocumentDbSecretUpdate(
            self, 
            "DocumentDbSecretUpdate", 
            props=db_props
        )


    # Dictionary of properties to be passed to other stacks  
    @property
    def docdb_info(self) -> dict:
        return {
            "secret-name": self.documentdb_secret.secret_name,
            "documentdb_sg_id": self.documentdb_security_group.security_group_id,
            "resource_id": self.document_db.attr_cluster_resource_id,   
            "username": self.documentdb_master_user,     
        }
    