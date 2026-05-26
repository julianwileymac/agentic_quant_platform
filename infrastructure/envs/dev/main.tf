###############################################################################
# envs/dev — full workload-environment composition.
###############################################################################

module "vpc" {
  source = "../../modules/vpc"
  name   = "aqp-dev"
  cidr   = "10.10.0.0/16"
}

module "eks" {
  source             = "../../modules/eks-cluster"
  cluster_name       = "aqp-dev"
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  kms_key_arn        = var.kms_key_arn
}

module "node_groups" {
  source       = "../../modules/eks-node-groups"
  cluster_name = module.eks.cluster_name
  subnet_ids   = module.vpc.private_subnet_ids
}

module "karpenter" {
  source            = "../../modules/karpenter-bootstrap"
  cluster_name      = module.eks.cluster_name
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_provider_url = module.eks.oidc_provider_url
  node_role_arn     = module.node_groups.general_node_role_arn
  depends_on        = [module.node_groups]
}

module "rds" {
  source      = "../../modules/rds-postgres"
  name        = "aqp-admin-dev"
  vpc_id      = module.vpc.vpc_id
  subnet_ids  = module.vpc.private_subnet_ids
  kms_key_arn = var.kms_key_arn
  multi_az    = false
}

module "msk" {
  source      = "../../modules/msk-kafka"
  name        = "aqp-dev"
  vpc_id      = module.vpc.vpc_id
  subnet_ids  = module.vpc.private_subnet_ids
  kms_key_arn = var.kms_key_arn
}

module "data_lake" {
  source      = "../../modules/s3-data-lake"
  name        = "aqp-data-lake-dev-${var.account_id}"
  kms_key_arn = var.kms_key_arn
}

module "eso" {
  source            = "../../modules/eso-bootstrap"
  cluster_name      = module.eks.cluster_name
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_provider_url = module.eks.oidc_provider_url
  kms_key_arn       = var.kms_key_arn
  account_id        = var.account_id
  region            = var.region
}

module "argocd" {
  source         = "../../modules/argocd-bootstrap"
  argocd_domain  = var.argocd_domain
  oidc_issuer    = var.argocd_oidc_issuer
  oidc_client_id = var.argocd_oidc_client_id
  rbac_csv       = file("${path.module}/argocd-rbac.csv")
}

module "observability" {
  source                 = "../../modules/observability-stack"
  grafana_admin_password = var.grafana_admin_password
}

module "github_actions_role" {
  source            = "../../modules/github-oidc"
  name              = "aqp-dev-github-actions-deploy"
  oidc_provider_arn = var.github_oidc_provider_arn
  github_org        = "julianwileymac"
  github_repo       = "agentic_quant_platform"
  ref_patterns      = ["refs/heads/main"]
  policy_arns       = ["arn:aws:iam::aws:policy/AdministratorAccess"]
}

output "cluster_name" { value = module.eks.cluster_name }
output "cluster_endpoint" { value = module.eks.cluster_endpoint }
output "vpc_id" { value = module.vpc.vpc_id }
output "rds_endpoint" { value = module.rds.instance_endpoint }
output "msk_brokers" { value = module.msk.bootstrap_brokers_sasl_iam }
