terraform {
  required_version = ">= 1.10"

  required_providers {
    azuread = {
      source                = "hashicorp/azuread"
      version               = "~> 3.0"
      configuration_aliases = [azuread]
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}
