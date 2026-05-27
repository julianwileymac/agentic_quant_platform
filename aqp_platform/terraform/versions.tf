terraform {
  required_version = ">= 1.10"

  required_providers {
    # Cloud providers — each module's resources gate on
    # ``var.cloud_provider`` so unused providers don't try to
    # authenticate at plan time.
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }

    # Kubernetes + Helm — always required because every cloud target
    # ends up provisioning a cluster + bootstrap Helm charts.
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.15"
    }

    # Local + Docker provider — powers the ``local`` cloud_provider
    # path and the LocalComposeAdapter's docker-compose fallback.
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    auth0 = {
      source  = "auth0/auth0"
      version = "~> 1.11"
    }
    # Microsoft Entra ID (Azure AD) — Workstream "Entra internal tenant"
    # (docs/plans/entra-internal-tenant-rollout.md). The aqp_entra_directory
    # module lands every staff app registration, service principal,
    # group, app-role assignment, federated credential, and named-location
    # under Terraform control. CA policies are read by data source only;
    # creation requires manual P2 review by Security.
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    # Management Engine Phase D — Cloudflare Zero Trust edge (tunnels,
    # DNS, Access apps). 5.6+ ships zero_trust_tunnel_cloudflared +
    # zero_trust_access_application + dns_record as first-class
    # resources matching the in-AQP CloudflareEdgeAdapter shape.
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.6"
    }
  }
}
