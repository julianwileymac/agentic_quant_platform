bucket       = "aqp-tfstate-prod"
key          = "prod/main.tfstate"
region       = "us-east-1"
encrypt      = true
kms_key_id   = "alias/aqp-tfstate"
use_lockfile = true
