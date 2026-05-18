import {
  Activity,
  AppWindow,
  BarChart3,
  Beaker,
  Bot,
  Boxes,
  Brain,
  CircuitBoard,
  CloudUpload,
  Code2,
  Compass,
  Database,
  FileBarChart,
  FlaskConical,
  Folder,
  GanttChartSquare,
  Gauge,
  GitBranch,
  Globe2,
  Grid3x3,
  Hammer,
  Handshake,
  History,
  Home,
  Layers,
  LineChart,
  ListChecks,
  Map as MapIcon,
  MessageSquare,
  Network,
  Notebook,
  Power,
  Radio,
  Rocket,
  Settings,
  Sparkles,
  Telescope,
  Users,
  Wallet,
  Wand2,
  Workflow,
  Zap,
} from "lucide-react";
import type { ComponentType } from "react";

export type NavGroup =
  | "Workspace"
  | "Bots"
  | "Tenancy"
  | "Agents"
  | "RAG"
  | "Research"
  | "Metadata"
  | "Lab"
  | "Execution"
  | "Workflows"
  | "Admin"
  | "System";

export type NavSubmenu = "ML" | "Data Management" | "Data Pipelines";

export interface NavItem {
  key: string;
  label: string;
  href: string;
  icon: ComponentType<{ className?: string }>;
  group: NavGroup;
  submenu?: NavSubmenu;
  hotkey?: string;
}

/**
 * Mirrors the existing webui/components/shell/nav-config.tsx so the
 * new Vite + Tailwind frontend lands at exactly the same URLs. Every
 * route here is implemented in src/routes/ — Phase 1 ships a small
 * subset (Live, Action Center, Dashboard) and the remaining entries
 * resolve to a stub page with a "Coming soon" placeholder until the
 * porting phases land.
 */
export const NAV_ITEMS: NavItem[] = [
  { key: "home", label: "Dashboard", href: "/", icon: Home, group: "Workspace" },
  {
    key: "live",
    label: "Live Trading Desk",
    href: "/live",
    icon: Radio,
    group: "Workspace",
  },
  {
    key: "action-center",
    label: "Action Center",
    href: "/action-center",
    icon: Power,
    group: "Workspace",
  },
  { key: "chat", label: "Chat", href: "/chat", icon: MessageSquare, group: "Workspace" },

  { key: "bots", label: "Bots", href: "/bots", icon: Bot, group: "Bots" },
  { key: "bots-new", label: "New Bot", href: "/bots/new", icon: Sparkles, group: "Bots" },

  { key: "strategies", label: "Strategies", href: "/strategies", icon: AppWindow, group: "Research" },

  {
    key: "data-catalog",
    label: "Data Catalog",
    href: "/data/catalog",
    icon: Folder,
    group: "Research",
    submenu: "Data Management",
  },
  {
    key: "data-iceberg",
    label: "Iceberg Editor",
    href: "/data/iceberg",
    icon: GitBranch,
    group: "Research",
    submenu: "Data Management",
  },
  {
    key: "data-explorer",
    label: "Data Workspace",
    href: "/data/explorer",
    icon: Database,
    group: "Research",
    submenu: "Data Management",
  },
  {
    key: "data-browser",
    label: "Data Browser",
    href: "/data/browser",
    icon: Layers,
    group: "Research",
    submenu: "Data Management",
  },
  {
    key: "visualizations",
    label: "Visualizations",
    href: "/visualizations",
    icon: BarChart3,
    group: "Research",
    submenu: "Data Management",
  },
  {
    key: "entity-graph",
    label: "Entity Graph",
    href: "/data/entity-graph",
    icon: Network,
    group: "Research",
    submenu: "Data Management",
  },
  {
    key: "alpha-vantage",
    label: "Alpha Vantage",
    href: "/alpha-vantage",
    icon: LineChart,
    group: "Research",
    submenu: "Data Management",
  },
  {
    key: "data-cfpb",
    label: "CFPB Complaints",
    href: "/data/cfpb",
    icon: Database,
    group: "Research",
    submenu: "Data Management",
  },
  { key: "data-fda", label: "FDA", href: "/data/fda", icon: Database, group: "Research", submenu: "Data Management" },
  {
    key: "data-uspto",
    label: "USPTO",
    href: "/data/uspto",
    icon: Database,
    group: "Research",
    submenu: "Data Management",
  },

  {
    key: "data-dbt",
    label: "dbt Models",
    href: "/data/dbt",
    icon: Code2,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "data-ingest",
    label: "Data Ingest",
    href: "/data/ingest",
    icon: CloudUpload,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "data-pipelines",
    label: "Data Pipelines",
    href: "/data/pipelines",
    icon: Workflow,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "data-pipelines-hub",
    label: "Pipelines Hub",
    href: "/data/pipelines/hub",
    icon: GanttChartSquare,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "data-hub",
    label: "Data Hub",
    href: "/data/hub",
    icon: Boxes,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "data-discovery",
    label: "Discovery",
    href: "/data/discovery",
    icon: Telescope,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "data-sandbox",
    label: "Sandbox",
    href: "/data/sandbox",
    icon: FlaskConical,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "data-sinks",
    label: "Sinks",
    href: "/data/sinks",
    icon: Database,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "data-sources",
    label: "Sources",
    href: "/data/sources",
    icon: Network,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "data-datasets-library",
    label: "Dataset Library",
    href: "/data/datasets/library",
    icon: Folder,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "data-dataset-configs",
    label: "Project Datasets",
    href: "/data/datasets/configs",
    icon: ListChecks,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "service-manager",
    label: "Service Manager",
    href: "/data/services",
    icon: Hammer,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "airbyte",
    label: "Airbyte",
    href: "/airbyte",
    icon: CloudUpload,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "airbyte-connectors",
    label: "Airbyte Connectors",
    href: "/airbyte/connectors",
    icon: Database,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "airbyte-builder",
    label: "Airbyte Builder",
    href: "/airbyte/builder",
    icon: FlaskConical,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "airbyte-runs",
    label: "Airbyte Runs",
    href: "/airbyte/runs",
    icon: Activity,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "streaming-kafka",
    label: "Kafka",
    href: "/streaming/kafka",
    icon: GitBranch,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "streaming-flink",
    label: "Flink",
    href: "/streaming/flink",
    icon: Zap,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "streaming-producers",
    label: "Producers",
    href: "/streaming/producers",
    icon: CloudUpload,
    group: "Research",
    submenu: "Data Pipelines",
  },
  {
    key: "wf-data",
    label: "Data Pipeline Editor",
    href: "/workflows/data",
    icon: Workflow,
    group: "Research",
    submenu: "Data Pipelines",
  },

  { key: "data-indicators", label: "Indicator Catalog", href: "/data/indicators", icon: FlaskConical, group: "Research" },
  { key: "data-live", label: "Live Market", href: "/data/live", icon: Zap, group: "Research" },
  { key: "factors", label: "Factor Workbench", href: "/factors", icon: Sparkles, group: "Research" },
  { key: "feature-sets", label: "Feature Sets", href: "/features", icon: Sparkles, group: "Research" },
  { key: "kg", label: "Knowledge Graph", href: "/data/kg", icon: Network, group: "Research" },
  {
    key: "data-microstructure",
    label: "Microstructure",
    href: "/data/microstructure",
    icon: Network,
    group: "Research",
  },
  { key: "research-equity", label: "Equity Research", href: "/research", icon: Sparkles, group: "Research" },
  { key: "learn", label: "Learn / Taxonomy", href: "/learn", icon: Sparkles, group: "Research" },
  { key: "learn-sources", label: "Source Libraries", href: "/learn/sources", icon: Compass, group: "Research" },

  {
    key: "metadata-aspects-list",
    label: "Aspect Browser",
    href: "/metadata/aspects",
    icon: Database,
    group: "Metadata",
  },
  {
    key: "metadata-aspects-stats",
    label: "Aspect Stats",
    href: "/metadata/aspects?tab=stats",
    icon: History,
    group: "Metadata",
  },
  {
    key: "metadata-aspects-lineage",
    label: "Lineage Explorer",
    href: "/metadata/aspects/lineage",
    icon: Network,
    group: "Metadata",
  },

  // Consolidated strategy authoring + testing umbrella. See
  // docs/strategy-development.md. Replaces the fragmented ml-test entry
  // (factor workbench / backtest list / monte carlo / optimizer remain
  // standalone because they are *consumption*, not authoring, surfaces).
  {
    key: "strategy-dev",
    label: "Strategy Development",
    href: "/strategy-development",
    icon: Beaker,
    group: "Lab",
  },
  { key: "backtest", label: "Backtests", href: "/backtest", icon: LineChart, group: "Lab" },
  { key: "optimizer", label: "Optimizer", href: "/optimizer", icon: Gauge, group: "Lab" },
  { key: "monte-carlo", label: "Monte Carlo", href: "/monte-carlo", icon: FlaskConical, group: "Lab" },

  { key: "ml", label: "ML Training", href: "/ml/training", icon: Brain, group: "Lab", submenu: "ML" },
  { key: "ml-builder", label: "ML Builder", href: "/ml/builder", icon: CircuitBoard, group: "Lab", submenu: "ML" },
  { key: "ml-datasets", label: "ML Datasets", href: "/ml/datasets", icon: Database, group: "Lab", submenu: "ML" },
  // `/ml/test` superseded by the consolidated `/strategy-development/*`
  // surface above. The flat route still exists in REAL_ROUTES so old
  // bookmarks keep working until the legacy webui retires.
  { key: "ml-models", label: "ML Models", href: "/ml/models", icon: Grid3x3, group: "Lab", submenu: "ML" },
  { key: "ml-zoo", label: "ML Model Zoo", href: "/ml/zoo", icon: Sparkles, group: "Lab", submenu: "ML" },

  { key: "rl", label: "RL", href: "/rl", icon: Bot, group: "Lab" },
  { key: "rl-lab", label: "RL Lab", href: "/rl/lab", icon: CircuitBoard, group: "Lab" },
  { key: "analysis-lab", label: "Analysis Lab", href: "/analysis/lab", icon: Telescope, group: "Lab" },
  { key: "rl-zoo", label: "RL Agent Zoo", href: "/rl/zoo", icon: Bot, group: "Lab" },
  { key: "options-lab", label: "Options Lab", href: "/options/lab", icon: FlaskConical, group: "Lab" },

  { key: "agents-templates", label: "Agent Templates", href: "/agents/templates", icon: Bot, group: "Agents" },
  { key: "agents-home", label: "Agents", href: "/agents", icon: Bot, group: "Agents" },
  { key: "agents-registry", label: "Agent Registry", href: "/agents/registry", icon: Grid3x3, group: "Agents" },
  { key: "agents-runs", label: "Agent Runs", href: "/agents/runs", icon: Activity, group: "Agents" },
  { key: "agents-evaluations", label: "Evaluations", href: "/agents/evaluations", icon: FlaskConical, group: "Agents" },
  { key: "agents-research", label: "Research Agents", href: "/agents/research", icon: Telescope, group: "Agents" },
  { key: "agents-selection", label: "Selection Agent", href: "/agents/selection", icon: AppWindow, group: "Agents" },
  { key: "agents-trader", label: "Trader Agent", href: "/agents/trader", icon: Zap, group: "Agents" },
  { key: "agents-analysis", label: "Analysis Agents", href: "/agents/analysis", icon: BarChart3, group: "Agents" },
  // Hybrid agentic-RL Phase 4 — Alpha Researcher + Strategy Executor.
  { key: "agents-quant", label: "Quant Agents", href: "/agents/quant", icon: FlaskConical, group: "Agents" },

  { key: "rag-explorer", label: "RAG Explorer", href: "/rag", icon: Network, group: "RAG" },
  { key: "rag-admin", label: "RAG Admin", href: "/rag/admin", icon: Settings, group: "RAG" },

  { key: "paper", label: "Paper Runs", href: "/paper", icon: Zap, group: "Execution" },
  { key: "portfolio", label: "Portfolio", href: "/portfolio", icon: Wallet, group: "Execution" },
  { key: "monitor", label: "Monitor", href: "/monitor", icon: Activity, group: "Execution" },
  { key: "crew", label: "Crew Trace", href: "/crew", icon: Bot, group: "Execution" },

  // Additive orchestration refactor (Phase 5) — Workflow Studio surfaces the
  // hash-locked WorkflowSpec registry + WorkflowRuntime dispatches. Lives
  // alongside the existing crew / strategy editors.
  { key: "wf-studio", label: "Workflow Studio", href: "/workflows", icon: Workflow, group: "Workflows" },
  { key: "wf-agent", label: "Agent Crew Editor", href: "/workflows/agent", icon: Workflow, group: "Workflows" },
  { key: "wf-strategy", label: "Strategy Composer", href: "/workflows/strategy", icon: Workflow, group: "Workflows" },

  { key: "explorer", label: "Resource Explorer", href: "/explorer", icon: Compass, group: "Tenancy" },

  { key: "admin-orgs", label: "Organizations", href: "/admin/orgs", icon: Globe2, group: "Admin" },
  { key: "admin-teams", label: "Teams", href: "/admin/teams", icon: Users, group: "Admin" },
  { key: "admin-users", label: "Users", href: "/admin/users", icon: Users, group: "Admin" },
  { key: "admin-workspaces", label: "Workspaces", href: "/admin/workspaces", icon: Folder, group: "Admin" },
  { key: "admin-projects", label: "Projects", href: "/admin/projects", icon: AppWindow, group: "Admin" },
  { key: "admin-labs", label: "Labs", href: "/admin/labs", icon: FlaskConical, group: "Admin" },
  { key: "admin-onboarding", label: "Onboarding", href: "/admin/onboarding", icon: Handshake, group: "Admin" },
  // Phase 7 — Infrastructure / Terraform IaC control plane.
  { key: "infra", label: "Infrastructure", href: "/infra", icon: CircuitBoard, group: "System" },
  { key: "infra-terraform", label: "Terraform IaC", href: "/infra/terraform", icon: Hammer, group: "System" },
  { key: "admin-configs", label: "Layered Config", href: "/admin/configs", icon: Settings, group: "Admin" },

  { key: "models", label: "Models & Providers", href: "/models", icon: Bot, group: "System" },
  { key: "ide", label: "Python IDE", href: "/ide", icon: Code2, group: "System" },
  { key: "docs", label: "Docs", href: "/docs", icon: Notebook, group: "System" },
  { key: "settings", label: "Settings", href: "/settings", icon: Settings, group: "System" },
];

export const GROUP_ORDER: NavGroup[] = [
  "Workspace",
  "Bots",
  "Tenancy",
  "Agents",
  "RAG",
  "Research",
  "Metadata",
  "Lab",
  "Execution",
  "Workflows",
  "Admin",
  "System",
];

export const SUBMENU_ORDER: NavSubmenu[] = ["Data Pipelines", "Data Management", "ML"];

const SUBMENU_ICONS: Record<NavSubmenu, ComponentType<{ className?: string }>> = {
  "Data Pipelines": CloudUpload,
  ML: Brain,
  "Data Management": Database,
};

export function getSubmenuIcon(submenu: NavSubmenu): ComponentType<{ className?: string }> {
  return SUBMENU_ICONS[submenu];
}

/**
 * Helper used by the sidebar to compute the active item from a path.
 */
export function findActiveNavItem(pathname: string): NavItem | undefined {
  const pathOnly = (href: string): string => {
    const [withoutQuery] = href.split("?");
    const [withoutHash] = (withoutQuery ?? href).split("#");
    return withoutHash || "/";
  };
  return NAV_ITEMS.filter(
    (n) => {
      const hrefPath = pathOnly(n.href);
      if (hrefPath === "/") {
        return pathname === "/";
      }
      return pathname === hrefPath || pathname.startsWith(`${hrefPath}/`);
    },
  ).sort((a, b) => pathOnly(b.href).length - pathOnly(a.href).length)[0];
}

/** Map known icons used by the action center / kill switch / inline UI. */
export const SHELL_ICONS = {
  rocket: Rocket,
  fileBarChart: FileBarChart,
  history: History,
  handshake: Handshake,
  wand: Wand2,
  map: MapIcon,
};
