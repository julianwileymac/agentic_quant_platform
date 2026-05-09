import {
  Activity,
  AppWindow,
  BarChart3,
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
  Map,
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

  { key: "backtest", label: "Backtests", href: "/backtest", icon: LineChart, group: "Lab" },
  { key: "optimizer", label: "Optimizer", href: "/optimizer", icon: Gauge, group: "Lab" },
  { key: "monte-carlo", label: "Monte Carlo", href: "/monte-carlo", icon: FlaskConical, group: "Lab" },

  { key: "ml", label: "ML Training", href: "/ml/training", icon: Brain, group: "Lab", submenu: "ML" },
  { key: "ml-builder", label: "ML Builder", href: "/ml/builder", icon: CircuitBoard, group: "Lab", submenu: "ML" },
  { key: "ml-datasets", label: "ML Datasets", href: "/ml/datasets", icon: Database, group: "Lab", submenu: "ML" },
  { key: "ml-test", label: "ML Test", href: "/ml/test", icon: FlaskConical, group: "Lab", submenu: "ML" },
  { key: "ml-models", label: "ML Models", href: "/ml/models", icon: Grid3x3, group: "Lab", submenu: "ML" },
  { key: "ml-zoo", label: "ML Model Zoo", href: "/ml/zoo", icon: Sparkles, group: "Lab", submenu: "ML" },

  { key: "rl", label: "RL", href: "/rl", icon: Bot, group: "Lab" },
  { key: "rl-lab", label: "RL Lab", href: "/rl/lab", icon: CircuitBoard, group: "Lab" },
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

  { key: "rag-explorer", label: "RAG Explorer", href: "/rag", icon: Network, group: "RAG" },
  { key: "rag-admin", label: "RAG Admin", href: "/rag/admin", icon: Settings, group: "RAG" },

  { key: "paper", label: "Paper Runs", href: "/paper", icon: Zap, group: "Execution" },
  { key: "portfolio", label: "Portfolio", href: "/portfolio", icon: Wallet, group: "Execution" },
  { key: "monitor", label: "Monitor", href: "/monitor", icon: Activity, group: "Execution" },
  { key: "crew", label: "Crew Trace", href: "/crew", icon: Bot, group: "Execution" },

  { key: "wf-agent", label: "Agent Crew Editor", href: "/workflows/agent", icon: Workflow, group: "Workflows" },
  { key: "wf-strategy", label: "Strategy Composer", href: "/workflows/strategy", icon: Workflow, group: "Workflows" },

  { key: "explorer", label: "Resource Explorer", href: "/explorer", icon: Compass, group: "Tenancy" },

  { key: "admin-orgs", label: "Organizations", href: "/admin/orgs", icon: Globe2, group: "Admin" },
  { key: "admin-teams", label: "Teams", href: "/admin/teams", icon: Users, group: "Admin" },
  { key: "admin-users", label: "Users", href: "/admin/users", icon: Users, group: "Admin" },
  { key: "admin-workspaces", label: "Workspaces", href: "/admin/workspaces", icon: Folder, group: "Admin" },
  { key: "admin-projects", label: "Projects", href: "/admin/projects", icon: AppWindow, group: "Admin" },
  { key: "admin-labs", label: "Labs", href: "/admin/labs", icon: FlaskConical, group: "Admin" },
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
  return NAV_ITEMS.filter(
    (n) => pathname === n.href || pathname.startsWith(`${n.href}/`),
  ).sort((a, b) => b.href.length - a.href.length)[0];
}

/** Map known icons used by the action center / kill switch / inline UI. */
export const SHELL_ICONS = {
  rocket: Rocket,
  fileBarChart: FileBarChart,
  history: History,
  handshake: Handshake,
  wand: Wand2,
  map: Map,
};
