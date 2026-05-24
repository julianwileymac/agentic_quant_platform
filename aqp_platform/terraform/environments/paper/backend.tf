terraform {
  backend "gcs" {
    bucket = "wiley-tech-aqp-terraform-state"
    prefix = "paper"
  }
}
