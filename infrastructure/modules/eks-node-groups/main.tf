###############################################################################
# modules/eks-node-groups — managed node groups (general baseline).
#
# Karpenter v1 manages compute / gpu / spot pools dynamically. This
# module ships only the always-on `general` group so the cluster has
# capacity for system addons before Karpenter boots.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "cluster_name" { type = string }
variable "subnet_ids" { type = list(string) }
variable "instance_types" {
  type    = list(string)
  default = ["m6i.large", "m6i.xlarge"]
}
variable "min_size" {
  type    = number
  default = 2
}
variable "max_size" {
  type    = number
  default = 10
}
variable "desired_size" {
  type    = number
  default = 3
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_eks_node_group" "general" {
  cluster_name    = var.cluster_name
  node_group_name = "${var.cluster_name}-general"
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = var.subnet_ids

  scaling_config {
    desired_size = var.desired_size
    max_size     = var.max_size
    min_size     = var.min_size
  }

  update_config {
    max_unavailable_percentage = 33
  }

  instance_types = var.instance_types
  ami_type       = "AL2023_x86_64_STANDARD"

  labels = {
    workload = "general"
  }

  tags = merge(var.tags, {
    "k8s.io/cluster-autoscaler/${var.cluster_name}" = "owned"
  })
}

resource "aws_iam_role" "node" {
  name = "${var.cluster_name}-general-node"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "node_worker" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "node_cni" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "node_ecr" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "node_ssm" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
