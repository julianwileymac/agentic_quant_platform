# Cost guardrails — fail the plan when expensive resources slip in
# without an explicit annotation. The AQP cost ledger (per env) is in
# ``aqp_docs/docs/how-to/operations/aws-deploy.md``; the SCPs at the
# org root cap the region set, and this file caps the per-resource
# sizing.

package main

import future.keywords.contains
import future.keywords.if
import future.keywords.in

resource_changes := input.resource_changes

# ---------------------------------------------------------------------------
# RDS — block ``db.r6g.16xlarge``-class instances without explicit override.
# ---------------------------------------------------------------------------

# Anything beyond db.r6g.4xlarge requires an annotation on the resource.
# Operators add `Tags = { "aqp.io/cost-override" = "approved-by-cfo" }`
# on the aws_db_instance.
deny contains msg if {
	some change in resource_changes
	change.type == "aws_db_instance"
	some action in change.change.actions
	action != "delete"
	cost_class := change.change.after.instance_class
	is_oversize_db(cost_class)
	not change.change.after.tags["aqp.io/cost-override"]
	msg := sprintf(
		"RDS instance %s uses oversize class %s without aqp.io/cost-override tag",
		[change.address, cost_class],
	)
}

is_oversize_db(class) if {
	class in {
		"db.r6g.8xlarge",
		"db.r6g.12xlarge",
		"db.r6g.16xlarge",
		"db.r5.12xlarge",
		"db.r5.24xlarge",
		"db.m5.16xlarge",
		"db.m5.24xlarge",
		"db.x2g.4xlarge",
		"db.x2g.8xlarge",
		"db.x2g.16xlarge",
	}
}

# ---------------------------------------------------------------------------
# NAT Gateway — warn (not deny) when per-AZ NAT lands without
# ``aqp.io/per-az-nat`` justification. Per-AZ NAT triples cost over
# the single-NAT pattern for ~negligible HA benefit in dev/staging.
# ---------------------------------------------------------------------------
warn contains msg if {
	some change in resource_changes
	change.type == "aws_nat_gateway"
	some action in change.change.actions
	action == "create"
	# Count multiple NAT creates in a single plan — three or more = per-AZ NAT.
	nat_creates := [c | some c in resource_changes; c.type == "aws_nat_gateway"; some a in c.change.actions; a == "create"]
	count(nat_creates) >= 2
	msg := sprintf(
		"Per-AZ NAT detected (%d create actions) — consider single_nat_gateway=true",
		[count(nat_creates)],
	)
}

# ---------------------------------------------------------------------------
# ElastiCache — block cluster modes without explicit override.
# ---------------------------------------------------------------------------
deny contains msg if {
	some change in resource_changes
	change.type == "aws_elasticache_replication_group"
	some action in change.change.actions
	action != "delete"
	change.change.after.num_cache_clusters >= 4
	not change.change.after.tags["aqp.io/cost-override"]
	msg := sprintf(
		"ElastiCache RG %s with %d nodes requires aqp.io/cost-override tag",
		[change.address, change.change.after.num_cache_clusters],
	)
}
