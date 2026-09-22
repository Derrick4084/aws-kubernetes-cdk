# AWS EKS LLM & Spark Infrastructure

AWS CDK Python project for deploying an **Amazon EKS 1.36 cluster** with Karpenter-based node scaling.

## Overview

This project provisions an EKS environment designed to run both **LLM inference workloads** and **Apache Spark jobs**.

### Key Components

* **Amazon EKS 1.36** — Kubernetes cluster deployed with AWS CDK.
* **Karpenter** — Automatically provisions and scales EC2 worker nodes based on workload requirements.
* **LLM Workloads** — Karpenter provisions GPU-capable nodes for LLM inference.
* **Apache Spark** — Spark jobs run on dynamically provisioned Karpenter nodes.
* **Amazon S3** — Used for persistent storage of model and application data.
* **Amazon FSx for Lustre** — Provides high-performance shared storage for LLM model weights.
* **Spark Operator** — Manages Spark applications running on Kubernetes.

## Current LLM

The current revision is configured to use:

**Meta Llama 3.1 8B Instruct**

`meta-llama/Llama-3.1-8B-Instruct`

Model weights are stored on S3/FSx for Lustre and made available to the LLM workload at runtime.

## Architecture

```text
                    AWS VPC
                       │
                 ┌─────▼─────┐
                 │ EKS 1.36  │
                 └─────┬─────┘
                       │
                 ┌─────▼─────┐
                 │ Karpenter │
                 └─────┬─────┘
                       │
          ┌────────────┴────────────┐
          │                         │
     LLM Workloads             Spark Jobs
          │                         │
     GPU EC2 Nodes             EC2 Nodes
          │                         │
          └──────────┬──────────────┘
                     │
              ┌──────▼──────┐
              │ S3 / FSx    │
              │   Lustre    │
              └─────────────┘
```

## Deployment

Install the CDK dependencies:

```bash
pip install -r requirements.txt
```

Bootstrap CDK if required:

```bash
cdk bootstrap
```

Deploy the infrastructure:

```bash
cdk deploy
```

## Project Status

This repository represents the current revision of the infrastructure. The configuration is being developed to support scalable **LLM inference and Spark workloads on EKS using Karpenter**.
