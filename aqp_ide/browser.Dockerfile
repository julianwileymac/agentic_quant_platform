# Builder stage
FROM node:24-bookworm AS build-stage

# install required tools to build the application
RUN apt-get update && apt-get install -y libxkbfile-dev libsecret-1-dev

WORKDIR /home/theia

# Copy repository files
COPY . .

# Remove unnecesarry files for the browser application
# Download plugins and build application production mode
# Use yarn autoclean to remove unnecessary files from package dependencies
#
# NOTE: install without --pure-lockfile so the AQP extension's @auth0/*
# dependencies (added in package.json but not yet pinned in yarn.lock)
# can resolve at build time. For fully-reproducible builds, regenerate
# yarn.lock on a machine with yarn 1.x:
#     docker run --rm -v "$(pwd)":/work -w /work node:24-bookworm \
#         bash -c "corepack disable && yarn install"
# and commit the resulting yarn.lock, then this command can be tightened
# back to `yarn --pure-lockfile` (or `yarn --frozen-lockfile`).
RUN yarn config set network-timeout 600000 -g && \
    yarn install && \
    yarn build:extensions && \
    yarn download:plugins && \
    yarn browser build && \
    yarn && \
    yarn autoclean --init && \
    echo *.ts >> .yarnclean && \
    echo *.ts.map >> .yarnclean && \
    echo *.spec.* >> .yarnclean && \
    yarn autoclean --force && \
    yarn cache clean && \
    rm -rf .git applications/electron theia-extensions/launcher theia-extensions/updater node_modules

# Production stage uses a small base image
FROM node:24-bookworm-slim AS production-stage

# Create theia user and directories
# Application will be copied to /home/theia
# Default workspace is located at /home/project
RUN adduser --system --group --home /home/theia theia
RUN chmod g+rw /home && \
    mkdir -p /home/project && \
    chown -R theia:theia /home/theia && \
    chown -R theia:theia /home/project;

# Install required tools for application: Temurin JDK, JDK, SSH, Bash, Maven
# Node is already available in base image
RUN apt-get update && apt-get install -y wget apt-transport-https && \
    apt-get update && apt-get install -y git openssh-client openssh-server bash libsecret-1-0 openjdk-17-jdk maven && \
    apt-get purge -y wget && \
    apt-get clean

ENV HOME=/home/theia
WORKDIR /home/theia

# Copy application from builder-stage
COPY --from=build-stage --chown=theia:theia /home/theia /home/theia

EXPOSE 3000

# Specify default shell for Theia and the Built-In plugins directory
ENV SHELL=/bin/bash \
    THEIA_DEFAULT_PLUGINS=local-dir:/home/theia/plugins

# Use installed git instead of dugite
ENV USE_LOCAL_GIT=true

# --- AQP Theia extension (theia-aqp-ext) runtime configuration ---
#
# These values are read by the Theia Node backend at request time and
# served to the browser bundle via GET /aqp/config. None are baked into
# the JS bundle - operators can change them per environment without
# rebuilding the image. All Auth0 SPA values are public by design (PKCE
# makes the client_id safe to expose).
#
# Required for Auth0 login to work:
#   AQP_THEIA_AUTH0_DOMAIN     - e.g. your-tenant.us.auth0.com
#   AQP_THEIA_AUTH0_CLIENT_ID  - SPA application client_id
#   AQP_THEIA_AUTH0_AUDIENCE   - must equal AQP backend's AQP_AUTH_OIDC_AUDIENCE
#   AQP_THEIA_PUBLIC_ORIGIN    - public origin of this Theia (e.g. http://localhost:3000)
#                                used to default AQP_THEIA_AUTH0_REDIRECT_URI
#
# Optional:
#   AQP_THEIA_AUTH0_SCOPE         - default 'openid profile email offline_access'
#   AQP_THEIA_AUTH0_REDIRECT_URI  - default '${AQP_THEIA_PUBLIC_ORIGIN}/'
#                                   (trailing slash MUST match Auth0 Allowed Callback URLs)
#   AQP_THEIA_AUTH0_ORGANIZATION  - Auth0 Organization id, when using Orgs
#   AQP_THEIA_API_URL             - AQP FastAPI base URL (default http://host.docker.internal:8000)
#
# Management Engine (Phase F of aqp_management_engine plan):
#   AQP_THEIA_FRONTEND_URL    - AQP Vite frontend origin so the embedded
#                               ManagementWidget iframe can target /manage,
#                               /cluster-mgmt, and /cloudflare directly.
#                               Falls back to AQP_THEIA_API_URL when unset.
#   AQP_THEIA_PROVIDERS_URL   - full URL of the BFF /auth/providers endpoint.
#                               Defaults to '${AQP_THEIA_API_URL}/auth/providers'.
#
# AQP MCP bridge (theia-ide-aqp-mcp-bridge-ext, AQP rule 49):
#   AQP_THEIA_MCP_DATA_URL          - streamable HTTP endpoint of aqp-data-mcp
#                                     (e.g. https://api.aqp.fund/mcp/data)
#   AQP_THEIA_MCP_DATA_AUDIENCE     - canonical URI advertised by the data
#                                     MCP server's RFC 9728 PRM document
#   AQP_THEIA_MCP_CODEBASE_URL      - streamable HTTP endpoint of
#                                     aqp-codebase-mcp
#   AQP_THEIA_MCP_CODEBASE_AUDIENCE - canonical URI for the codebase MCP
#
# AQP Research Copilot (theia-ide-aqp-research-copilot-ext, AQP rule 2):
#   AQP_THEIA_SERA_ENABLED          - "true" to default code-focused agents
#                                     to AQP's SERA-32B model (see
#                                     aqp_docs/docs/concepts/data/sera.md). Off by default.
#   AQP_THEIA_ROUTER_COMPLETE_PATH  - override the default
#                                     /llm/router/complete path (rare).
ENV AQP_THEIA_AUTH0_DOMAIN="" \
    AQP_THEIA_AUTH0_CLIENT_ID="" \
    AQP_THEIA_AUTH0_AUDIENCE="" \
    AQP_THEIA_AUTH0_SCOPE="openid profile email offline_access" \
    AQP_THEIA_AUTH0_REDIRECT_URI="" \
    AQP_THEIA_AUTH0_ORGANIZATION="" \
    AQP_THEIA_API_URL="http://host.docker.internal:8000" \
    AQP_THEIA_FRONTEND_URL="" \
    AQP_THEIA_PROVIDERS_URL="" \
    AQP_THEIA_PUBLIC_ORIGIN="http://localhost:3000" \
    AQP_THEIA_MCP_DATA_URL="" \
    AQP_THEIA_MCP_DATA_AUDIENCE="" \
    AQP_THEIA_MCP_CODEBASE_URL="" \
    AQP_THEIA_MCP_CODEBASE_AUDIENCE="" \
    AQP_THEIA_SERA_ENABLED="false" \
    AQP_THEIA_ROUTER_COMPLETE_PATH=""

# Switch to Theia user
USER theia
WORKDIR /home/theia/applications/browser

# Launch the backend application via node
ENTRYPOINT [ "node", "/home/theia/applications/browser/lib/backend/main.js" ]

# Arguments passed to the application
CMD [ "/home/project", "--hostname=0.0.0.0" ]
