variable "cloud_provider" { type = string }
variable "environment" { type = string }
variable "common_tags" {
  type    = map(string)
  default = {}
}
variable "image_names" {
  type    = list(string)
  default = ["aqp-api", "aqp-worker", "aqp-agent", "aqp-data-mcp", "aqp-frontend", "aqp-terraform-runner"]
}
variable "aws_region" {
  type    = string
  default = "us-east-1"
}
variable "gcp_project_id" {
  type    = string
  default = ""
}

variable "gcp_region" {
  type    = string
  default = "us-central1"
}
variable "azure_resource_group" {
  type    = string
  default = ""
}

variable "azure_location" {
  type    = string
  default = "eastus"
}

# Local Docker registry container (a single registry serves every image).
resource "docker_image" "registry" {
  count        = var.cloud_provider == "local" ? 1 : 0
  name         = "registry:2"
  keep_locally = true
}

resource "docker_container" "registry" {
  count = var.cloud_provider == "local" ? 1 : 0
  name  = "aqp-registry-${var.environment}"
  image = docker_image.registry[0].image_id
  ports {
    internal = 5000
    external = 5000
  }
}

# AWS ECR — one repo per image.
resource "aws_ecr_repository" "aqp" {
  for_each             = var.cloud_provider == "aws" ? toset(var.image_names) : []
  name                 = each.value
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
  tags = var.common_tags
}

resource "aws_ecr_lifecycle_policy" "aqp" {
  for_each   = var.cloud_provider == "aws" ? toset(var.image_names) : []
  repository = aws_ecr_repository.aqp[each.value].name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 10
        description  = "keep last 10 tagged images"
        selection = {
          tagStatus     = "tagged"
          countType     = "imageCountMoreThan"
          countNumber   = 10
          tagPrefixList = ["v", "latest", "main"]
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 20
        description  = "expire untagged after 14 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 14
        }
        action = { type = "expire" }
      },
    ]
  })
}

# GCP Artifact Registry — one Docker repo holds every image.
resource "google_artifact_registry_repository" "aqp" {
  count         = var.cloud_provider == "gcp" ? 1 : 0
  project       = var.gcp_project_id
  location      = var.gcp_region
  repository_id = "aqp-${var.environment}"
  format        = "DOCKER"
  labels        = var.common_tags
}

# Azure ACR.
resource "azurerm_container_registry" "aqp" {
  count               = var.cloud_provider == "azure" ? 1 : 0
  name                = replace("aqp${var.environment}", "-", "")
  resource_group_name = var.azure_resource_group
  location            = var.azure_location
  sku                 = "Standard"
  admin_enabled       = false
  tags                = var.common_tags
}

output "image_base_url" {
  description = "Prefix every Deployment uses for image URLs."
  value = coalesce(
    try("localhost:5000", var.cloud_provider == "local" ? "localhost:5000" : null),
    try(values(aws_ecr_repository.aqp)[0].repository_url, null) != null ? "${split("/", values(aws_ecr_repository.aqp)[0].repository_url)[0]}" : null,
    try("${var.gcp_region}-docker.pkg.dev/${var.gcp_project_id}/${google_artifact_registry_repository.aqp[0].repository_id}", null),
    try(azurerm_container_registry.aqp[0].login_server, null),
    "localhost:5000",
  )
}
