terraform {
  backend "azurerm" {
    resource_group_name  = "wiley-tech-aqp-rg"
    storage_account_name = "wileytechaqptfstate"
    container_name       = "terraform-state"
    key                  = "wiley-tech.terraform.tfstate"
  }
}
