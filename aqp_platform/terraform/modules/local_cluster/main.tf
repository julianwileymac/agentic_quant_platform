###############################################################################
# local_cluster — provision a k3d-in-Docker cluster + image registry.
#
# Replaces the docker-compose-driven local stack. The cluster is created
# idempotently via the ``k3d`` CLI (Terraform can't talk to k3d's HTTP
# API directly because k3d is a thin wrapper around the Docker SDK).
# Once the cluster is up, Helm + Kubernetes providers (configured at the
# environment level) take over and the rest of the AQP modules apply
# normally.
#
# Gating: every resource here uses ``count = local.is_local ? 1 : 0`` so
# the cloud paths stay untouched.
###############################################################################

terraform {
  required_providers {
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}

locals {
  is_local = var.cloud_provider == "local" || var.cloud_provider == "docker"
}

# ---------------------------------------------------------------------------
# Idempotent k3d cluster creation.
#
# The provisioner re-checks ``k3d cluster list`` before issuing ``k3d
# cluster create``. Re-running terraform apply on an already-running
# cluster is a no-op. Tear-down happens through ``terraform destroy``
# which fires the ``destroy`` provisioner below.
# ---------------------------------------------------------------------------

resource "null_resource" "cluster" {
  count = local.is_local ? 1 : 0

  triggers = {
    cluster_name            = var.cluster_name
    registry_name           = var.registry_name
    registry_port           = var.registry_port
    lb_http_port            = var.lb_http_port
    lb_https_port           = var.lb_https_port
    k3d_image               = var.k3d_image
    local_shell_interpreter = var.local_shell_interpreter
  }

  # Up: idempotent create. ``|| true`` swallows the existing-cluster
  # error so successive applies converge on the same target.
  provisioner "local-exec" {
    interpreter = [var.local_shell_interpreter, "-c"]
    command     = <<-EOT
      set -e
      if ! command -v k3d >/dev/null 2>&1; then
        echo "[local_cluster] k3d CLI not on PATH. Install via 'choco install k3d' (Windows), 'brew install k3d' (macOS), or curl install.k3d.io." >&2
        exit 127
      fi
      if k3d cluster list | awk '{print $1}' | grep -Fxq "${var.cluster_name}"; then
        echo "[local_cluster] cluster '${var.cluster_name}' already exists; skipping create."
      else
        echo "[local_cluster] creating cluster '${var.cluster_name}' with registry '${var.registry_name}:${var.registry_port}'."
        k3d cluster create "${var.cluster_name}" \
          --servers 1 \
          --agents 0 \
          --image "${var.k3d_image}" \
          --port "${var.lb_http_port}:80@loadbalancer" \
          --port "${var.lb_https_port}:443@loadbalancer" \
          --registry-create "${var.registry_name}:0.0.0.0:${var.registry_port}" \
          --wait
      fi
      mkdir -p "$(dirname "${var.kubeconfig_path}")"
      k3d kubeconfig get "${var.cluster_name}" | sed 's/host.docker.internal/127.0.0.1/g' > "${var.kubeconfig_path}"
      echo "[local_cluster] kubeconfig written to ${var.kubeconfig_path}."
    EOT
  }

  # Down: only fires on terraform destroy. Best-effort: never raises
  # so a partially-deleted cluster doesn't trap the state file.
  provisioner "local-exec" {
    when        = destroy
    interpreter = [try(self.triggers.local_shell_interpreter, "bash"), "-c"]
    command     = <<-EOT
      set +e
      if command -v k3d >/dev/null 2>&1; then
        k3d cluster delete "${self.triggers.cluster_name}" || true
      fi
    EOT
  }
}

# ---------------------------------------------------------------------------
# Provider readiness barrier.
#
# Some cloud-flavoured installs hit a race between the k3d API server
# coming up and the kubernetes/helm providers trying to authenticate.
# This null_resource just sleeps for ~5s after cluster creation so the
# first kubernetes_namespace apply doesn't fail with a transient
# 'connection refused'.
# ---------------------------------------------------------------------------

resource "null_resource" "wait_for_api" {
  count = local.is_local ? 1 : 0

  depends_on = [null_resource.cluster]

  triggers = {
    cluster_name            = var.cluster_name
    local_shell_interpreter = var.local_shell_interpreter
  }

  provisioner "local-exec" {
    interpreter = [var.local_shell_interpreter, "-c"]
    command     = "sleep 5"
  }
}
