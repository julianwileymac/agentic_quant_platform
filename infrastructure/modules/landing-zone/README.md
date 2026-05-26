# modules/landing-zone

Establishes the multi-account topology + Control Tower SCPs.

Apply only from the AWS Org **management account**. Re-applying from
a workload account fails because `aws_organizations_organization`
requires master-account context.
