terraform {
  backend "s3" {
    bucket         = "wiley-tech-aqp-terraform-state"
    key            = "live/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "wiley-tech-aqp-terraform-locks"
    encrypt        = true
  }
}
