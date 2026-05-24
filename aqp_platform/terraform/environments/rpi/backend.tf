terraform {
  backend "local" {
    path = "../../../data/terraform/state/rpi.tfstate"
  }
}
