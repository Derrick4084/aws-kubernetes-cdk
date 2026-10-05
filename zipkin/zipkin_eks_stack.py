import yaml
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_eks as eks,
    CfnOutput
)
from constructs import Construct


class ZipkinEksStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, cluster: eks.Cluster, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)


        with open("zipkin/zipkin-eks.yaml", "r") as f:
            manifests = [
                manifest
                for manifest in yaml.safe_load_all(f)
                if manifest is not None
            ]
        cluster.add_manifest(
            "ZipkinDeploymentManifest",
            *manifests
        )

    @property
    def zipkin_info(self) -> dict:
        return {
            "host": "zipkin.ecomm.svc.cluster.local",
            "port": "9411"
    }