// sidebars.ts — Agentic Quant Platform documentation IA.
//
// Diátaxis-style top-level cuts:
//   intro/           — quickstart, glossary, repo orientation
//   tutorials/       — runnable, learning-oriented walkthroughs
//   how-to/          — task-oriented recipes (operations + runbooks + mlops)
//   concepts/        — explanation-oriented narrative (system understanding)
//   reference/       — information-oriented (API, Python, data dictionary)
//   architecture/    — ADRs + preprocessing spec
//   release-notes/   — Changesets-emitted customer-facing notes
//   archive/         — historical context, no operational guidance
//
// Each sidebar is referenced from docusaurus.config.ts navbar items.

import type { SidebarsConfig } from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  introSidebar: [
    {
      type: 'category',
      label: 'Get started',
      collapsed: false,
      items: [
        'intro/index',
        'intro/quickstart',
        'intro/installation',
        'intro/glossary',
        'intro/repository-orientation',
        'intro/conventions',
      ],
    },
  ],

  conceptsSidebar: [
    {
      type: 'category',
      label: 'Platform',
      collapsed: false,
      items: [
        'concepts/platform/architecture',
        'concepts/platform/domain-model',
        'concepts/platform/core-types',
        'concepts/platform/erd',
        'concepts/platform/class-diagram',
        'concepts/platform/flows',
        'concepts/platform/repository-split',
        'concepts/platform/aqp-monorepo-paths',
        'concepts/platform/code-index-governance',
        'concepts/platform/legacy-types-shim',
        'concepts/platform/temporal-identifiers',
        'concepts/platform/instrument-taxonomy',
        'concepts/platform/scopes',
        'concepts/platform/entity-registry',
        'concepts/platform/entity-graph-services',
        'concepts/platform/contingency-graphs',
        'concepts/platform/experiments-tests',
        'concepts/platform/ownership-graph',
        'concepts/platform/local-platform',
      ],
    },
    {
      type: 'category',
      label: 'Data plane',
      items: [
        'concepts/data/data-plane',
        'concepts/data/data-catalog',
        'concepts/data/data-self-service',
        'concepts/data/datasets-catalog',
        'concepts/data/metadata-cache',
        'concepts/data/data-discovery',
        'concepts/data/airbyte-builder',
        'concepts/data/dagster',
        'concepts/data/dagster-sandbox',
        'concepts/data/data-products',
        'concepts/data/data-mcp',
        'concepts/data/data-engine',
        'concepts/data/data-pipelines-hub',
        'concepts/data/data-layer-unification',
        'concepts/data/visualization-layer',
        'concepts/data/pgvector-control-plane',
        'concepts/data/codebase-mcp',
        'concepts/data/sera',
        'concepts/data/analytics-frontend',
        'concepts/data/agent-watchdog',
        'concepts/data/alpha-vantage',
        'concepts/data/futures-curves',
        'concepts/data/streaming',
        'concepts/data/streaming-admin',
        'concepts/data/live-market',
        'concepts/data/regulatory-data',
        'concepts/data/redpanda',
        'concepts/data/questdb',
        'concepts/data/phoenix',
        'concepts/data/hudi',
        'concepts/data/datahub-sync',
        'concepts/data/pricing-context',
        'concepts/data/research-papers-rag',
        'concepts/data/rag',
        'concepts/data/mcp-risk-tools',
        'concepts/data/accounts-balances',
        'concepts/data/order-types',
        'concepts/data/reconciliation',
        'concepts/data/providers',
      ],
    },
    {
      type: 'category',
      label: 'Strategy + ML',
      items: [
        'concepts/strategy/analysis-framework',
        'concepts/strategy/analysis-lab',
        'concepts/strategy/analysis-flows',
        'concepts/strategy/analysis-agents',
        'concepts/strategy/factor-research',
        'concepts/strategy/ml-framework',
        'concepts/strategy/ml-libraries',
        'concepts/strategy/ml-alpha-backtest',
        'concepts/strategy/ml-flows',
        'concepts/strategy/ml-preprocessing-pipeline',
        'concepts/strategy/ml-builder',
        'concepts/strategy/ml-testing',
        'concepts/strategy/backtest-engines',
        'concepts/strategy/vbtpro-integration',
        'concepts/strategy/hft-backtest',
        'concepts/strategy/optimal-control',
        'concepts/strategy/portfolio-options-mm',
        'concepts/strategy/microstructure-toxicity',
        'concepts/strategy/strategy-lifecycle',
        'concepts/strategy/strategy-browser',
        'concepts/strategy/strategy-development',
        'concepts/strategy/strategy-templates',
        'concepts/strategy/predictor-hub',
        'concepts/strategy/execution-paths',
        'concepts/strategy/cross-market-arbitrage',
        'concepts/strategy/statistical-arbitrage',
      ],
    },
    {
      type: 'category',
      label: 'Reinforcement learning',
      items: [
        'concepts/rl/rl-framework',
        'concepts/rl/rl-lab',
        'concepts/rl/rl-components',
        'concepts/rl/rl-iceberg',
        'concepts/rl/rl-policy-backbones',
        'concepts/rl/rl-market-dynamics',
        'concepts/rl/rl-finagent',
        'concepts/rl/rl-prudex-evaluation',
        'concepts/rl/agentic-rl',
        'concepts/rl/weight-centric-pipeline',
      ],
    },
    {
      type: 'category',
      label: 'Agentic',
      items: [
        'concepts/agentic/agentic-development',
        'concepts/agentic/agentic-pipeline',
        'concepts/agentic/agents',
        'concepts/agentic/multi-agent-patterns',
        'concepts/agentic/workflow-studio',
        'concepts/agentic/orchestration-refactor-rollout',
        'concepts/agentic/alpha-researcher-agent',
        'concepts/agentic/research-agents',
        'concepts/agentic/trader-agents',
        'concepts/agentic/selection-agents',
        'concepts/agentic/bots',
      ],
    },
    {
      type: 'category',
      label: 'Trading + operations',
      items: [
        'concepts/trading/paper-trading',
        'concepts/trading/paper-metadata-gate',
        'concepts/trading/observability',
        'concepts/trading/observability-stack',
        'concepts/trading/webui',
      ],
    },
    {
      type: 'category',
      label: 'Identity + tenancy',
      items: [
        'concepts/identity/identity',
        'concepts/identity/account-management',
        'concepts/identity/credentials',
        'concepts/identity/cloud-credentials',
        'concepts/identity/auth0-setup',
        'concepts/identity/auth0-actions',
        'concepts/identity/auth0-microsoft-federation',
        'concepts/identity/msal-entra-setup',
        'concepts/identity/scim-provisioning',
        'concepts/identity/multi-tenancy',
        'concepts/identity/management-engine',
      ],
    },
    {
      type: 'category',
      label: 'Infrastructure',
      items: [
        'concepts/infrastructure/aqp-ide',
        'concepts/infrastructure/aqp-ide-roadmap',
        'concepts/infrastructure/kubernetes-adapter',
        'concepts/infrastructure/kubernetes-rpi-deployment',
        'concepts/infrastructure/control-plane-topology',
        'concepts/infrastructure/terraform-control-plane',
        'concepts/infrastructure/iac-runbook',
      ],
    },
  ],

  howToSidebar: [
    {
      type: 'category',
      label: 'Operations',
      collapsed: false,
      items: [
        'how-to/operations/local-setup',
        'how-to/operations/kubernetes-deploy',
        'how-to/operations/tower-cluster-deploy',
        'how-to/operations/aqp-fund-blue-green-cutover',
        'how-to/operations/edge-deploy',
        'how-to/operations/incident-response',
        'how-to/operations/kill-switch-incident-response',
        'how-to/operations/auth0-k8s-checklist',
        'how-to/operations/rotate-secrets',
        'how-to/operations/rts6-validation-report-generation',
        'how-to/operations/hft-node-onboarding',
        'how-to/operations/bot-canary-rollout-playbook',
        'how-to/operations/add-new-provider',
        'how-to/operations/configuration-management',
      ],
    },
    {
      type: 'category',
      label: 'Runbooks',
      items: [
        'how-to/runbooks/dr-restore',
        'how-to/runbooks/quota-exhaustion',
        'how-to/runbooks/snapshot-deadlock',
        'how-to/runbooks/questdb-wal-stall',
      ],
    },
    {
      type: 'category',
      label: 'MLOps',
      items: [
        'how-to/mlops/serving',
        'how-to/mlops/cross-repo-lineage',
        'how-to/mlops/k8s-deployment',
      ],
    },
    {
      type: 'category',
      label: 'Recipes',
      items: [
        'how-to/recipes/index',
        'how-to/recipes/add-a-strategy',
        'how-to/recipes/run-a-backtest-from-yaml',
        'how-to/recipes/promote-a-bot-to-paper',
        'how-to/recipes/snapshot-an-agent-spec',
        'how-to/recipes/query-data-via-mcp',
      ],
    },
  ],

  tutorialsSidebar: [
    {
      type: 'category',
      label: 'Tutorials',
      collapsed: false,
      items: [
        'tutorials/index',
        'tutorials/first-backtest',
        'tutorials/first-bot',
        'tutorials/first-rl-experiment',
        'tutorials/first-agent-workflow',
        'tutorials/first-paper-trading-session',
      ],
    },
  ],

  referenceSidebar: [
    {
      type: 'category',
      label: 'API reference',
      collapsed: false,
      items: [
        'reference/api/index',
      ],
    },
    {
      type: 'category',
      label: 'Control-plane API',
      items: [
        'reference/manage-api/index',
      ],
    },
    {
      type: 'category',
      label: 'Python reference',
      items: [
        'reference/python/index',
      ],
    },
    {
      type: 'category',
      label: 'Data dictionary',
      items: [
        'reference/data-dictionary/index',
      ],
    },
  ],

  architectureSidebar: [
    {
      type: 'category',
      label: 'Decisions',
      collapsed: false,
      items: [
        'architecture/decisions/static-export-over-ssr',
        'architecture/decisions/single-container-client',
        'architecture/decisions/auth0-zero-trust',
        'architecture/decisions/provider-abstraction',
        'architecture/decisions/separated-control-plane',
        'architecture/decisions/quantbot-operator-pattern',
        'architecture/decisions/quantbot-latency-classes',
        'architecture/decisions/quantbot-event-sourcing',
        'architecture/decisions/quantbot-rts6-conformance',
        'architecture/decisions/quantbot-canary-pnl-gates',
        'architecture/decisions/rl-production-enhancement',
      ],
    },
    {
      type: 'category',
      label: 'Specifications',
      items: ['architecture/preprocessing-spec'],
    },
  ],

  archiveSidebar: [
    {
      type: 'category',
      label: 'Archive',
      collapsed: true,
      items: [
        'archive/README',
        'archive/audit_report',
        'archive/verification_report',
        'archive/IMPLEMENTATION_PROMPT',
        'archive/AQP_REFACTOR_MASTER_PROMPT',
        'archive/aqp-enhancement-plan',
      ],
    },
  ],
};

export default sidebars;
