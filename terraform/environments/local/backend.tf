terraform {
  backend "local" {
    path = "../../../data/terraform/state/local.tfstate"
  }
}
