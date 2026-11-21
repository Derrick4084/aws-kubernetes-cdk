import yaml
from aws_cdk import (
    Stack,
    aws_eks as eks,
)
from constructs import Construct


class LlmManifestStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, 
            cluster: eks.ICluster,
            lustre_info: dict,
            karpenter_chart, 
            **kwargs
        ) -> None:
        super().__init__(scope, construct_id, **kwargs)


        '''
        Karpenter restart job to restart the karpenter deployment 
        to validate the nodepool and provisioner changes are applied correctly.
        '''
        karpenter_restart_sa = cluster.add_manifest(
            "KarpenterRestartSA",
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {
                    "name": "karpenter-restarter", 
                    "namespace": "karpenter"
                },
            }
        )
        karpenter_restart_sa.node.add_dependency(karpenter_chart)


        karpenter_restart_rbac = cluster.add_manifest(
            "KarpenterRestartRBAC",
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "Role",
                "metadata": {
                    "name": "karpenter-restarter", 
                    "namespace": "karpenter"
                },
                "rules": [
                    {
                        "apiGroups": ["apps"],
                        "resources": ["deployments"],
                        "verbs": ["get", "patch"],
                    }
                ],
            }
        )
        karpenter_restart_rolebinding = cluster.add_manifest(
            "KarpenterRestartRoleBinding",
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "RoleBinding",
                "metadata": {
                    "name": "karpenter-restarter", 
                    "namespace": "karpenter"
                },
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "Role",
                    "name": "karpenter-restarter",
                },
                "subjects": [
                    {
                        "kind": "ServiceAccount", 
                        "name": "karpenter-restarter", 
                        "namespace": "karpenter"
                    }
                ],
            }
        )
        karpenter_restart_rolebinding.node.add_dependency(karpenter_restart_rbac)
          
        karpenter_restart = cluster.add_manifest(
            "KarpenterRestartJob",
            {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "metadata": {
                    "name": "karpenter-restart", 
                    "namespace": "karpenter"
                },
                "spec": {
                    "ttlSecondsAfterFinished": 120,
                    "template": {
                        "spec": {
                            "serviceAccountName": "karpenter-restarter",
                            "restartPolicy": "OnFailure",
                            "containers": [
                                {
                                "name": "kubectl",
                                "image": "bitnami/kubectl:latest",
                                "command": [
                                    "kubectl", 
                                    "rollout", 
                                    "restart",
                                    "deployment/karpenter", 
                                    "-n", 
                                    "karpenter"
                                ],
                            }],
                        }
                    },
                },
            }
        )
        karpenter_restart.node.add_dependency(karpenter_restart_rolebinding)



        # Download models into FSX persistant volume
        model_download = cluster.add_manifest("model-download", 
            yaml.safe_load(open("llm/model-download.yaml").read().format(      
                model_bucket=lustre_info['fsx-bucket-name'],
        )))
        model_download.node.add_dependency(karpenter_restart)
        

        # Download embeddings into FSX persistant volume
        embedding_download = cluster.add_manifest("embeddings-download", 
            yaml.safe_load(open("llm/embedding-download.yaml").read().format(      
                model_bucket=lustre_info['fsx-bucket-name'],
        )))
        embedding_download.node.add_dependency(karpenter_restart)
        

        # Deploy LLM and Embedding models
        # Depends on model download and embedding download
        with open("llm/model-deployment.yaml", "r") as f:
            model_deploy_manifests = [
                manifest
                for manifest in yaml.safe_load_all(f)
                if manifest is not None
            ]

        with open("llm/embedding-deployment.yaml", "r") as f:
            embedding_deploy_manifests = [
                manifest
                for manifest in yaml.safe_load_all(f)
                if manifest is not None
            ] 
    
          
        cluster.add_manifest(
            "ModelDeploymentManifest",
            *model_deploy_manifests
        ).node.add_dependency(model_download)


        cluster.add_manifest(
            "EmbeddingDeploymentManifest",
            *embedding_deploy_manifests
        ).node.add_dependency(embedding_download)

    
                