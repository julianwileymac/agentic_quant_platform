bucket       = "aqp-tfstate-staging"
key          = "staging/main.tfstate"
region       = "us-east-1"
encrypt      = true
kms_key_id   = "alias/aqp-tfstate"
use_lockfile = true
