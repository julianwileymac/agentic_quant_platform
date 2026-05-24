terraform {
  backend "local" {
    path = "../../../data/terraform/state/tower.tfstate"
  }
}
