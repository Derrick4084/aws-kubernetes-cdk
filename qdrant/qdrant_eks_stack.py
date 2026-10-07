import yaml
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_eks as eks,
    CfnOutput
)
from constructs import Construct


class QdrantEksStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, 
            cluster: eks.Cluster, 
            **kwargs
        ) -> None:
        super().__init__(scope, construct_id, **kwargs)


        
        with open("qdrant/qdrant-eks.yaml", "r") as f:
            manifests = [
                manifest
                for manifest in yaml.safe_load_all(f)
                if manifest is not None
            ]
        cluster.add_manifest(
            "QdrantDeploymentManifest",
            *manifests
        )

    @property
    def qdrant_info(self) -> dict:
        return {
            "host": "qdrant.ecomm.svc.cluster.local",
            "port": "6334",
        }