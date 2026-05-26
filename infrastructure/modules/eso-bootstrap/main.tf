###############################################################################
# modules/eso-bootstrap — External Secrets Operator + AWS SM ClusterSecretStore.
#
# Provisions IRSA + Helm + the ClusterSecretStore CRD so any AQP
# namespace can reference `aqp/*` secrets from AWS Secrets Manager
# via plain `kind: ExternalSecret` resources.
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
variable "kms_key_arn" { type = string }
variable "account_id" { type = string }
variable "region" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}

###############################################################################
# IRSA — let the operator read aqp/* secrets and decrypt with our KMS key.
###############################################################################

data "aws_iam_policy_document" "eso_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(var.oidc_provider_url, "https://", "")}:sub"
      values   = ["system:serviceaccount:external-secrets:external-secrets"]
    }
  }
}

resource "aws_iam_role" "eso" {
  name               = "${var.cluster_name}-external-secrets"
  assume_role_policy = data.aws_iam_policy_document.eso_assume.json
}

resource "aws_iam_policy" "eso" {
  name = "${var.cluster_name}-external-secrets"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadAqpSecrets"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetResourcePolicy",
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
          "secretsmanager:ListSecretVersionIds",
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath",
        ]
        Resource = [
          "arn:aws:secretsmanager:${var.region}:${var.account_id}:secret:aqp/*",
          "arn:aws:ssm:${var.region}:${var.account_id}:parameter/aqp/*",
        ]
      },
      {
        Sid      = "DecryptWithPlatformKey"
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = var.kms_key_arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "eso" {
  role       = aws_iam_role.eso.name
  policy_arn = aws_iam_policy.eso.arn
}

###############################################################################
# Helm release.
###############################################################################

resource "helm_release" "external_secrets" {
  name             = "external-secrets"
  repository       = "https://charts.external-secrets.io"
  chart            = "external-secrets"
  version          = "0.10.7"
  namespace        = "external-secrets"
  create_namespace = true

  set { name = "serviceAccount.name", value = "external-secrets" }
  set {
    name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = aws_iam_role.eso.arn
  }
  set { name = "installCRDs", value = "true" }
}

###############################################################################
# ClusterSecretStore CRD — every namespace reads from this.
###############################################################################

resource "kubernetes_manifest" "cluster_secret_store" {
  manifest = {
    apiVersion = "external-secrets.io/v1beta1"
    kind       = "ClusterSecretStore"
    metadata   = { name = "aws-secrets" }
    spec = {
      provider = {
        aws = {
          service = "SecretsManager"
          region  = var.region
          auth = {
            jwt = {
              serviceAccountRef = {
                name      = "external-secrets"
                namespace = "external-secrets"
              }
            }
          }
        }
      }
    }
  }
  depends_on = [helm_release.external_secrets]
}
