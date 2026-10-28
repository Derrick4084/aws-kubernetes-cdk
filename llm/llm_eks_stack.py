import yaml
from aws_cdk import (
    Stack,
    aws_eks as eks,
)
from constructs import Construct

from configs.roles import RoleStatements


class LlmEksStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, 
            cluster: eks.ICluster,
            lustre_info: dict,
            karpenter_node_role_name: str, 
            **kwargs
        ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        role_statements = RoleStatements()

        model_storage_pod_id_role = role_statements.model_storage_pod_id_role_stmt(
            self, 
            fsx_bucket_arn=lustre_info["fsx-bucket-arn"]
        )

        
        eks.ServiceAccount(
            self,
            "ModelStorageServiceAccount",
            cluster=cluster,
            name="model-storage",
            namespace="ecomm",
        )
           
        eks.CfnPodIdentityAssociation(
            self,
            "ModelStoragePodIdentityAssociation",
            cluster_name=cluster.cluster_name,
            namespace="ecomm",
            service_account="model-storage",
            role_arn=model_storage_pod_id_role.role_arn,
        )
        

        # Persistant volume for LLM and embeddings model download
        model_pv = cluster.add_manifest("model-pv", 
                yaml.safe_load(open("lustre/lustre-pv.yaml").read().format(
                    fsx_id=lustre_info["fsx-id"], 
                    fsx_dns_name=lustre_info["fsx-dns-name"],
                    fsx_mount_name=lustre_info["fsx-mount-name"]
        )))
   
        # Persistant volume claim for LLM and embeddings model storage
        model_pvc = cluster.add_manifest("model-pvc", 
                yaml.safe_load(open("lustre/lustre-pvc.yaml").read()))
        model_pvc.node.add_dependency(model_pv)

        # Download models into FSX persistant volume
        model_download = cluster.add_manifest("model-download", 
            yaml.safe_load(open("llm/model-download.yaml").read().format(      
                model_bucket=lustre_info['fsx-bucket-name'],
        )))
        model_download.node.add_dependency(model_pvc)

        # Download embeddings into FSX persistant volume
        embedding_download = cluster.add_manifest("embeddings-download", 
            yaml.safe_load(open("embedding/embedding-download.yaml").read().format(      
                model_bucket=lustre_info['fsx-bucket-name'],
        )))
        embedding_download.node.add_dependency(model_pvc)


        #  Karpenter Nodepools    
        cluster.add_manifest("ecomm-app-nodepool", 
                        yaml.safe_load(open("karpenter/ecomm-app-np.yaml").read()))

        cluster.add_manifest("embedding-nodepool", 
                        yaml.safe_load(open("karpenter/embedding-np.yaml").read()))

        cluster.add_manifest("model-nodepool", 
                        yaml.safe_load(open("karpenter/llm-gpu-np.yaml").read()))

        
        # Karpenter Nodeclasses  
        cluster.add_manifest("ecomm-app-nodeclass", 
                yaml.safe_load(open("karpenter/ecomm-app-nc.yaml").read().format(
                    role_name=karpenter_node_role_name, 
                    clustername=cluster.cluster_name
        )))
               
        cluster.add_manifest("embedding-nodeclass", 
                yaml.safe_load(open("karpenter/embedding-nc.yaml").read().format(
                    role_name=karpenter_node_role_name, 
                    clustername=cluster.cluster_name
        )))
        
        cluster.add_manifest("model-nodeclass", 
                yaml.safe_load(open("karpenter/llm-gpu-nc.yaml").read().format(
                    role_name=karpenter_node_role_name, 
                    clustername=cluster.cluster_name
        )))
        



        # Deploy LLM and Embedding models
        # Depends on model download and embedding download
        with open("llm/model-deployment.yaml", "r") as f:
            model_deploy_manifests = [
                manifest
                for manifest in yaml.safe_load_all(f)
                if manifest is not None
            ]

        with open("embedding/embedding-deployment.yaml", "r") as f:
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

    
                