import yaml
from aws_cdk import (
    Stack,
    aws_eks as eks
)
from constructs import Construct
from configs.helmvalues import HelmValues

   
class KarpenterK8sStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, cluster: eks.Cluster,
                queue_name: str, node_role_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        helm_values = HelmValues()
       
        karpenter_crds = cluster.add_helm_chart("KarpenterCRDs",
            chart="karpenter-crd",
            repository="oci://public.ecr.aws/karpenter/karpenter-crd",
            release="karpenter-crd",
            create_namespace=True,
            namespace="karpenter",
            version="1.14.1",
        )

        karpenter = cluster.add_helm_chart(
            "Karpenter",
            chart="karpenter",
            repository="oci://public.ecr.aws/karpenter/karpenter",
            release="karpenter",
            namespace="karpenter",
            version="1.14.1",
            values=helm_values.get_karpenter_values(
                clustername=cluster.cluster_name, 
                cluster_endpoint=cluster.cluster_endpoint,
                queue_name=queue_name
            )
        )
        karpenter.node.add_dependency(karpenter_crds)


        node_class = cluster.add_manifest("karpenter-nodeclass", 
                yaml.safe_load(open("karpenter/general-purpose-nc.yaml").read().format(
                    role_name=node_role_name, 
                    clustername=cluster.cluster_name)))
        node_class.node.add_dependency(karpenter)
        

        node_pool = cluster.add_manifest("karpenter-nodepool", 
                yaml.safe_load(open("karpenter/general-purpose-np.yaml").read()))
        node_pool.node.add_dependency(karpenter)


        llm_node_class = cluster.add_manifest("llm-nodeclass", 
                yaml.safe_load(open("llm/llm-gpu-nc.yaml").read().format(
                    role_name=node_role_name, 
                    clustername=cluster.cluster_name)))
        llm_node_class.node.add_dependency(karpenter)


        llm_node_pool = cluster.add_manifest("llm-nodepool", 
                yaml.safe_load(open("llm/llm-gpu-np.yaml").read()))
        llm_node_pool.node.add_dependency(karpenter)
        