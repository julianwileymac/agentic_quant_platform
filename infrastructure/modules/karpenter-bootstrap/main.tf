###############################################################################
# modules/karpenter-bootstrap — Karpenter v1 IRSA + Helm release + NodePools.
#
# Self-managed Karpenter (NOT EKS Auto Mode) so every NodePool spec is
# recorded under `terraform_stack_spec_versions` per AGENTS rule 43.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws        = { source = "hashicorp/aws",        version = "~> 5.70" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.32" }
    helm       = { source = "hashicorp/helm",       version = "~> 2.16" }
  }
}

variable "cluster_name" { type = string }
variable "oidc_provider_arn" { type = string }
variable "oidc_provider_url" { type = string }
variable "node_role_arn" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}

###############################################################################
# IRSA for the Karpenter controller.
###############################################################################

data "aws_iam_policy_document" "karpenter_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(var.oidc_provider_url, "https://", "")}:sub"
      values   = ["system:serviceaccount:karpenter:karpenter"]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(var.oidc_provider_url, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "karpenter" {
  name               = "${var.cluster_name}-karpenter-controller"
  assume_role_policy = data.aws_iam_policy_document.karpenter_assume.json
}

resource "aws_iam_policy" "karpenter" {
  name = "${var.cluster_name}-karpenter-controller"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EC2"
        Effect = "Allow"
        Action = [
          "ec2:CreateLaunchTemplate",
          "ec2:CreateFleet",
          "ec2:RunInstances",
          "ec2:CreateTags",
          "ec2:TerminateInstances",
          "ec2:DescribeInstances",
          "ec2:DescribeImages",
          "ec2:DescribeInstanceTypes",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeAvailabilityZones",
          "ec2:DescribeLaunchTemplates",
          "ec2:DescribeSpotPriceHistory",
          "pricing:GetProducts",
          "ssm:GetParameter",
          "iam:PassRole",
          "iam:CreateInstanceProfile",
          "iam:DeleteInstanceProfile",
          "iam:AddRoleToInstanceProfile",
          "iam:RemoveRoleFromInstanceProfile",
          "iam:TagInstanceProfile",
          "eks:DescribeCluster",
          "sqs:DeleteMessage",
          "sqs:GetQueueUrl",
          "sqs:ReceiveMessage",
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "karpenter" {
  role       = aws_iam_role.karpenter.name
  policy_arn = aws_iam_policy.karpenter.arn
}

###############################################################################
# Helm release.
###############################################################################

resource "helm_release" "karpenter" {
  name             = "karpenter"
  repository       = "oci://public.ecr.aws/karpenter"
  chart            = "karpenter"
  version          = "1.1.0"
  namespace        = "karpenter"
  create_namespace = true

  set {
    name  = "settings.clusterName"
    value = var.cluster_name
  }
  set {
    name  = "settings.interruptionQueue"
    value = var.cluster_name
  }
  set {
    name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = aws_iam_role.karpenter.arn
  }
  set {
    name  = "controller.resources.requests.cpu"
    value = "1"
  }
  set {
    name  = "controller.resources.requests.memory"
    value = "1Gi"
  }
}

###############################################################################
# NodePool + EC2NodeClass — three pools per blueprint §6.2.
###############################################################################

resource "kubernetes_manifest" "ec2_node_class_default" {
  manifest = {
    apiVersion = "karpenter.k8s.aws/v1"
    kind       = "EC2NodeClass"
    metadata   = { name = "default" }
    spec = {
      role         = element(split("/", var.node_role_arn), 1)
      amiSelectorTerms = [{ alias = "al2023@latest" }]
      subnetSelectorTerms = [{
        tags = { "karpenter.sh/discovery" = var.cluster_name }
      }]
      securityGroupSelectorTerms = [{
        tags = { "karpenter.sh/discovery" = var.cluster_name }
      }]
      tags = merge(var.tags, {
        "karpenter.sh/managed-by" = var.cluster_name
      })
    }
  }
  depends_on = [helm_release.karpenter]
}

resource "kubernetes_manifest" "node_pool_compute" {
  manifest = {
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata   = { name = "compute" }
    spec = {
      template = {
        metadata = {
          labels = { workload = "compute" }
        }
        spec = {
          requirements = [
            { key = "karpenter.sh/capacity-type", operator = "In", values = ["on-demand", "spot"] },
            { key = "node.kubernetes.io/instance-type", operator = "In", values = ["c6i.2xlarge", "c6i.4xlarge", "c6i.8xlarge"] },
          ]
          taints = [
            { key = "workload", value = "compute", effect = "NoSchedule" },
          ]
          nodeClassRef = {
            group = "karpenter.k8s.aws"
            kind  = "EC2NodeClass"
            name  = "default"
          }
        }
      }
      limits = { cpu = "1000", memory = "4000Gi" }
      disruption = {
        consolidationPolicy = "WhenEmptyOrUnderutilized"
        consolidateAfter    = "30s"
      }
    }
  }
  depends_on = [kubernetes_manifest.ec2_node_class_default]
}

resource "kubernetes_manifest" "node_pool_gpu" {
  manifest = {
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata   = { name = "gpu" }
    spec = {
      template = {
        metadata = { labels = { workload = "gpu" } }
        spec = {
          requirements = [
            { key = "karpenter.sh/capacity-type", operator = "In", values = ["on-demand"] },
            { key = "node.kubernetes.io/instance-type", operator = "In", values = ["g5.xlarge", "g5.2xlarge", "g5.4xlarge", "g5.12xlarge"] },
          ]
          taints = [
            { key = "nvidia.com/gpu", value = "present", effect = "NoSchedule" },
          ]
          nodeClassRef = {
            group = "karpenter.k8s.aws"
            kind  = "EC2NodeClass"
            name  = "default"
          }
        }
      }
      limits = { cpu = "200", memory = "1500Gi" }
    }
  }
  depends_on = [kubernetes_manifest.ec2_node_class_default]
}

resource "kubernetes_manifest" "node_pool_spot_backtests" {
  manifest = {
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata   = { name = "spot-backtests" }
    spec = {
      template = {
        metadata = { labels = { workload = "backtests" } }
        spec = {
          requirements = [
            { key = "karpenter.sh/capacity-type", operator = "In", values = ["spot"] },
            { key = "kubernetes.io/arch", operator = "In", values = ["amd64"] },
          ]
          taints = [
            { key = "workload", value = "backtests", effect = "NoSchedule" },
          ]
          nodeClassRef = {
            group = "karpenter.k8s.aws"
            kind  = "EC2NodeClass"
            name  = "default"
          }
        }
      }
      limits = { cpu = "5000", memory = "20000Gi" }
      disruption = {
        consolidationPolicy = "WhenEmpty"
        consolidateAfter    = "1m"
      }
    }
  }
  depends_on = [kubernetes_manifest.ec2_node_class_default]
}
