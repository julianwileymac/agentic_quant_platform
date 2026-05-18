###############################################################################
# aqp_images — build + push every AQP container image to the local k3d
# registry.
#
# Drives ``docker build`` + ``docker push`` per image. Every resource
# gates on local/docker so cloud installs use their own ECR/GCR/ACR
# pushes (see modules/registry).
#
# Per-image triggers fingerprint the relevant source dirs so we only
# rebuild when something actually changed. The fingerprints are
# intentionally narrow (Dockerfile + the package the image ships) so
# touching docs / configs / tests doesn't invalidate caches.
###############################################################################

terraform {
  required_providers {
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

locals {
  is_local = var.cloud_provider == "local" || var.cloud_provider == "docker"

  # Canonical image catalogue. Each entry maps the logical AQP service
  # name to (Dockerfile target, source tree fingerprint inputs). The
  # Dockerfile is multi-stage so every variant points at the same
  # ./Dockerfile but selects a different ``--target``.
  #
  # Fingerprints are computed via filemd5 on representative source
  # files. Add to ``fingerprint`` lists when an image starts depending
  # on a new source tree.
  images = {
    api = {
      target = "api"
      fingerprint = [
        "Dockerfile",
        "pyproject.toml",
        "aqp/api/main.py",
        "aqp/api/routes/scim.py",
        "aqp/api/routes/control_plane.py",
        "aqp/config/settings.py",
        "aqp/deployment/topology.py",
        "aqp/cli/main.py",
      ]
    }
    worker = {
      target = "api"
      fingerprint = [
        "Dockerfile",
        "pyproject.toml",
        "aqp/tasks/celery_app.py",
        "aqp/config/settings.py",
        "aqp/deployment/topology.py",
      ]
    }
    beat = {
      target = "api"
      fingerprint = [
        "Dockerfile",
        "pyproject.toml",
        "aqp/config/settings.py",
        "aqp/deployment/topology.py",
      ]
    }
    paper = {
      target = "paper"
      fingerprint = [
        "Dockerfile",
        "pyproject.toml",
      ]
    }
    serving = {
      target = "serving"
      fingerprint = [
        "Dockerfile",
        "pyproject.toml",
      ]
    }
    ingester = {
      target = "ingester"
      fingerprint = [
        "Dockerfile",
        "pyproject.toml",
        "aqp/streaming/cli.py",
      ]
    }
  }
}

# ---------------------------------------------------------------------------
# Backend images (api, worker, beat, paper, serving, ingester).
#
# Every image targets the same ``./Dockerfile``; only the multi-stage
# ``--target`` changes. Re-tagging api -> worker / beat re-uses the
# Docker layer cache so the per-stage build is fast.
# ---------------------------------------------------------------------------

resource "null_resource" "backend_image" {
  for_each = local.is_local ? local.images : {}

  triggers = {
    image_tag = "${var.registry_localhost}/aqp-${each.key}:${var.app_version}"
    target    = each.value.target
    # Fingerprint covers Dockerfile + source dirs; new files added to
    # ``aqp/`` do invalidate the cache via the Dockerfile copy step.
    fingerprint = sha256(join("|", [
      for f in each.value.fingerprint :
      fileexists("${var.context_path}/${f}") ? filemd5("${var.context_path}/${f}") : "missing"
    ]))
    ready_marker = var.ready_marker
  }

  provisioner "local-exec" {
    interpreter = [var.local_shell_interpreter, "-c"]
    command     = <<-EOT
      set -e
      cd "${var.context_path}"
      echo "[aqp_images] building aqp-${each.key} (target=${each.value.target}) -> ${self.triggers.image_tag}"
      docker build \
        --target ${each.value.target} \
        -t "${self.triggers.image_tag}" \
        -t "${var.registry_host}/aqp-${each.key}:${var.app_version}" \
        -f Dockerfile \
        .
      echo "[aqp_images] pushing aqp-${each.key} to ${var.registry_localhost}"
      docker push "${self.triggers.image_tag}"
    EOT
  }
}

# ---------------------------------------------------------------------------
# Frontend image — Vite build wrapped in nginx.
#
# Build assumes the bundle has already landed under
# ``frontend/dist/`` (the CLI's ``aqp deploy build`` runs ``pnpm
# build`` before terraform apply for module.aqp_images).
# ---------------------------------------------------------------------------

resource "null_resource" "frontend_image" {
  count = local.is_local ? 1 : 0

  triggers = {
    image_tag           = "${var.registry_localhost}/aqp-frontend:${var.app_version}"
    fingerprint         = fileexists("${var.context_path}/${var.frontend_dist_path}/index.html") ? filemd5("${var.context_path}/${var.frontend_dist_path}/index.html") : "missing"
    ready_marker        = var.ready_marker
    dockerfile_template = "nginx-spa-v3"
  }

  provisioner "local-exec" {
    interpreter = [var.local_shell_interpreter, "-c"]
    command     = <<-EOT
      set -e
      cd "${var.context_path}"
      if [ ! -d "${var.frontend_dist_path}" ]; then
        echo "[aqp_images] frontend dist missing at ${var.frontend_dist_path}; running 'pnpm --dir frontend build' first."
        pnpm --dir frontend build
      fi
      cat > frontend/Dockerfile.tf << 'DOCKER_EOF'
      FROM nginx:1.27-alpine
      COPY frontend/dist/ /usr/share/nginx/html/
      RUN printf 'server {\n  listen 80;\n  root /usr/share/nginx/html;\n  location / {\n    try_files $uri $uri/ /index.html;\n  }\n}\n' > /etc/nginx/conf.d/default.conf
      EXPOSE 80
      DOCKER_EOF
      docker build \
        -t "${self.triggers.image_tag}" \
        -t "${var.registry_host}/aqp-frontend:${var.app_version}" \
        -f frontend/Dockerfile.tf \
        .
      docker push "${self.triggers.image_tag}"
    EOT
  }
}
