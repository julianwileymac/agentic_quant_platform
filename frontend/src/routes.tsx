import type { ReactElement } from "react";
import { createBrowserRouter, type RouteObject } from "react-router-dom";

import { AppShell } from "@/components/shell/AppShell";

import { ActionCenterRoute } from "@/routes/action-center/page";
import { AirbyteRoute } from "@/routes/airbyte/page";
import { AlphaVantageRoute } from "@/routes/alpha-vantage/page";
import { AlphaVantageAdminRoute } from "@/routes/alpha-vantage/admin/page";
import {
  AlphaVantageCommoditiesRoute,
  AlphaVantageCryptoRoute,
  AlphaVantageEconomicsRoute,
  AlphaVantageForexRoute,
  AlphaVantageFundamentalsRoute,
  AlphaVantageIndicesRoute,
  AlphaVantageIntelligenceRoute,
  AlphaVantageOptionsRoute,
  AlphaVantageTechnicalsRoute,
  AlphaVantageTimeseriesRoute,
} from "@/routes/alpha-vantage/categories";
import { AirbyteBuilderRoute } from "@/routes/airbyte/builder/page";
import { AirbyteConnectorsRoute } from "@/routes/airbyte/connectors/page";
import { AirbyteRunsRoute } from "@/routes/airbyte/runs/page";
import { LabsAdminRoute } from "@/routes/admin/labs/page";
import { LayeredConfigsRoute } from "@/routes/admin/configs/page";
import { OrgsAdminRoute } from "@/routes/admin/orgs/page";
import { ProjectsAdminRoute } from "@/routes/admin/projects/page";
import { TeamsAdminRoute } from "@/routes/admin/teams/page";
import { UsersAdminRoute } from "@/routes/admin/users/page";
import { WorkspacesAdminRoute } from "@/routes/admin/workspaces/page";
import { AgentsHomeRoute } from "@/routes/agents/page";
import { AgentRegistryRoute } from "@/routes/agents/registry/page";
import { AgentsRunsRoute } from "@/routes/agents/runs/page";
import { AgentRunDetailRoute } from "@/routes/agents/runs/[id]/page";
import { AgentEvaluationsRoute } from "@/routes/agents/evaluations/page";
import { AgentTemplatesRoute } from "@/routes/agents/templates/page";
import { ResearchAgentsHubRoute } from "@/routes/agents/research/page";
import { ResearchEquityAgentRoute } from "@/routes/agents/research/equity/page";
import { ResearchNewsAgentRoute } from "@/routes/agents/research/news/page";
import { ResearchUniverseAgentRoute } from "@/routes/agents/research/universe/page";
import { AnalysisAgentsHubRoute } from "@/routes/agents/analysis/page";
import { AnalysisStepAgentRoute } from "@/routes/agents/analysis/step/page";
import { AnalysisRunAgentRoute } from "@/routes/agents/analysis/run/page";
import { AnalysisPortfolioAgentRoute } from "@/routes/agents/analysis/portfolio/page";
import { SelectionAgentRoute } from "@/routes/agents/selection/page";
import { TraderAgentRoute } from "@/routes/agents/trader/page";
import { BacktestRoute } from "@/routes/backtest/page";
import { BacktestDetailRoute } from "@/routes/backtest/[id]/page";
import { BacktestNewRoute } from "@/routes/backtest/new/page";
import { BotsRoute } from "@/routes/bots/page";
import { BotDetailRoute } from "@/routes/bots/[id]/page";
import { BotNewRoute } from "@/routes/bots/new/page";
import { BotBuilderRoute } from "@/routes/bots/builder/page";
import { ChatRoute } from "@/routes/chat/page";
import { CrewTraceRoute } from "@/routes/crew/page";
import { DashboardRoute } from "@/routes/dashboard/page";
import { DataCatalogRoute } from "@/routes/data/catalog/page";
import { DataCatalogTableDetailRoute } from "@/routes/data/catalog/[namespace]/[name]/page";
import { EntityGraphRoute } from "@/routes/data/entity-graph/page";
import { IcebergEditorRoute } from "@/routes/data/iceberg/page";
import { IndicatorCatalogRoute } from "@/routes/data/indicators/page";
import { KnowledgeGraphRoute } from "@/routes/data/kg/page";
import { DataSinksRoute } from "@/routes/data/sinks/page";
import { DataSourcesRoute } from "@/routes/data/sources/page";
import { FactorWorkbenchRoute } from "@/routes/factors/page";
import { FeatureSetsRoute } from "@/routes/features/page";
import { LearnRoute } from "@/routes/learn/page";
import { LearnSourcesRoute } from "@/routes/learn/sources/page";
import { ResearchRoute } from "@/routes/research/page";
import { ResearchEquityRoute } from "@/routes/research/equity/[symbol]/page";
import { CfpbRoute } from "@/routes/data/cfpb/page";
import { FdaRoute } from "@/routes/data/fda/page";
import { UsptoRoute } from "@/routes/data/uspto/page";
import { DatasetLibraryRoute } from "@/routes/data/datasets/library/page";
import { ProjectDatasetsRoute } from "@/routes/data/datasets/configs/page";
import { DataDatahubRoute } from "@/routes/data/datahub/page";
import { MicrostructureRoute } from "@/routes/data/microstructure/page";
import { DataEngineRoute } from "@/routes/data/engine/page";
import { DataEngineDetailRoute } from "@/routes/data/engine/[id]/page";
import { IcebergConsolidateRoute } from "@/routes/data/iceberg/consolidate/page";
import { DataHubRoute } from "@/routes/data/hub/page";
import { DataExplorerRoute } from "@/routes/data/explorer/page";
import { DataBrowserRoute } from "@/routes/data/browser/page";
import { DataSymbolBrowserRoute } from "@/routes/data/browser/[vt_symbol]/page";
import { LiveMarketRoute } from "@/routes/data/live/page";
import { DataIngestRoute } from "@/routes/data/ingest/page";
import { DataPipelinesRoute } from "@/routes/data/pipelines/page";
import { PipelinesHubRoute } from "@/routes/data/pipelines/hub/page";
import { ServiceManagerRoute } from "@/routes/data/services/page";
import { DbtModelsRoute } from "@/routes/data/dbt/page";
import { DocsRoute } from "@/routes/docs/page";
import { ResourceExplorerRoute } from "@/routes/explorer/page";
import { IdeRoute } from "@/routes/ide/page";
import { LiveDeskRoute } from "@/routes/live/page";
import { MlBuilderRoute } from "@/routes/ml/builder/page";
import { MlTrainingRoute } from "@/routes/ml/training/page";
import { ModelsProvidersRoute } from "@/routes/models/page";
import { MonitorRoute } from "@/routes/monitor/page";
import { MonteCarloRoute } from "@/routes/monte-carlo/page";
import { NotFoundRoute } from "@/routes/not-found";
import { OptimizerRoute } from "@/routes/optimizer/page";
import { OptionsLabRoute } from "@/routes/options/lab/page";
import { PaperRoute } from "@/routes/paper/page";
import { PortfolioRoute } from "@/routes/portfolio/page";
import { RagAdminRoute } from "@/routes/rag/admin/page";
import { RagExplorerRoute } from "@/routes/rag/page";
import { RlHomeRoute } from "@/routes/rl/page";
import { RlLabRoute } from "@/routes/rl/lab/page";
import { RlRunDetailRoute } from "@/routes/rl/runs/[id]/page";
import { RlReplayRoute } from "@/routes/rl/runs/[id]/replay/page";
import { RlRunsRoute } from "@/routes/rl/runs/page";
import { RlZooRoute } from "@/routes/rl/zoo/page";
import { RlLibraryRoute } from "@/routes/rl/library/page";
import { RlAgentBuilderRoute } from "@/routes/rl/builder/agent/page";
import { RlExperimentBuilderRoute } from "@/routes/rl/builder/experiment/page";
import { RlObservationBuilderRoute } from "@/routes/rl/builder/observation/page";
import { RlRewardBuilderRoute } from "@/routes/rl/builder/reward/page";
import { MlZooRoute } from "@/routes/ml/zoo/page";
import { MlModelsRoute } from "@/routes/ml/models/page";
import { MlDatasetsRoute } from "@/routes/ml/datasets/page";
import { MlTestRoute } from "@/routes/ml/test/page";
import { SettingsRoute } from "@/routes/settings/page";
import { StrategiesRoute } from "@/routes/strategies/page";
import { StrategyDetailRoute } from "@/routes/strategies/[id]/page";
import { FlinkRoute } from "@/routes/streaming/flink/page";
import { KafkaRoute } from "@/routes/streaming/kafka/page";
import { ProducersRoute } from "@/routes/streaming/producers/page";
import { KafkaTopicDetailRoute } from "@/routes/streaming/kafka/topics/[name]/page";
import { FlinkJobDetailRoute } from "@/routes/streaming/flink/jobs/[name]/page";
import { ProducerDetailRoute } from "@/routes/streaming/producers/[name]/page";
import { StrategyNewRoute } from "@/routes/strategies/new/page";
import { stubRoute } from "@/routes/stub";
import { VisualizationsRoute } from "@/routes/visualizations/page";
import { AgentCrewEditorRoute } from "@/routes/workflows/agent/page";
import { DataPipelineEditorRoute } from "@/routes/workflows/data/page";
import { StrategyComposerRoute } from "@/routes/workflows/strategy/page";

import { NAV_ITEMS } from "@/components/shell/nav-config";

/**
 * Routes implemented with real components. Anything in NAV_ITEMS that
 * isn't in this map renders a `stubRoute` placeholder explaining which
 * porting phase will fill it in.
 */
const REAL_ROUTES: Record<string, () => ReactElement> = {
  "/": DashboardRoute,
  "/live": LiveDeskRoute,
  "/action-center": ActionCenterRoute,
  "/chat": ChatRoute,
  "/bots": BotsRoute,
  "/bots/new": BotNewRoute,
  "/agents": AgentsHomeRoute,
  "/agents/registry": AgentRegistryRoute,
  "/agents/runs": AgentsRunsRoute,
  "/agents/templates": AgentTemplatesRoute,
  "/agents/evaluations": AgentEvaluationsRoute,
  "/agents/research": ResearchAgentsHubRoute,
  "/agents/analysis": AnalysisAgentsHubRoute,
  "/agents/selection": SelectionAgentRoute,
  "/agents/trader": TraderAgentRoute,
  // B2 — Airbyte
  "/airbyte": AirbyteRoute,
  "/airbyte/builder": AirbyteBuilderRoute,
  "/airbyte/connectors": AirbyteConnectorsRoute,
  "/airbyte/runs": AirbyteRunsRoute,
  // B3 — Alpha Vantage
  "/alpha-vantage": AlphaVantageRoute,
  // B4a — Data plane (medium)
  "/data/hub": DataHubRoute,
  "/data/explorer": DataExplorerRoute,
  "/data/browser": DataBrowserRoute,
  "/data/live": LiveMarketRoute,
  "/data/ingest": DataIngestRoute,
  "/data/pipelines": DataPipelinesRoute,
  "/data/pipelines/hub": PipelinesHubRoute,
  "/data/services": ServiceManagerRoute,
  "/data/dbt": DbtModelsRoute,
  // B4b — Regulatory
  "/data/cfpb": CfpbRoute,
  "/data/fda": FdaRoute,
  "/data/uspto": UsptoRoute,
  // B4c — Data plane (heavy)
  "/data/datasets/library": DatasetLibraryRoute,
  "/data/datasets/configs": ProjectDatasetsRoute,
  "/data/microstructure": MicrostructureRoute,
  // B6 — Research / Learn
  "/factors": FactorWorkbenchRoute,
  "/features": FeatureSetsRoute,
  "/learn": LearnRoute,
  "/learn/sources": LearnSourcesRoute,
  "/research": ResearchRoute,
  // B5 — Lab (ML + RL)
  "/ml/zoo": MlZooRoute,
  "/ml/models": MlModelsRoute,
  "/ml/datasets": MlDatasetsRoute,
  "/ml/test": MlTestRoute,
  "/rl/zoo": RlZooRoute,
  "/backtest": BacktestRoute,
  "/paper": PaperRoute,
  "/portfolio": PortfolioRoute,
  "/monitor": MonitorRoute,
  "/crew": CrewTraceRoute,
  "/ml/builder": MlBuilderRoute,
  "/ml/training": MlTrainingRoute,
  "/rl": RlHomeRoute,
  "/rl/lab": RlLabRoute,
  "/workflows/agent": AgentCrewEditorRoute,
  "/workflows/data": DataPipelineEditorRoute,
  "/workflows/strategy": StrategyComposerRoute,
  "/ide": IdeRoute,
  // Phase 3 — Research / Data
  "/strategies": StrategiesRoute,
  "/data/catalog": DataCatalogRoute,
  "/data/iceberg": IcebergEditorRoute,
  "/data/sources": DataSourcesRoute,
  "/data/sinks": DataSinksRoute,
  "/data/indicators": IndicatorCatalogRoute,
  "/data/entity-graph": EntityGraphRoute,
  "/data/kg": KnowledgeGraphRoute,
  "/visualizations": VisualizationsRoute,
  "/rag": RagExplorerRoute,
  "/rag/admin": RagAdminRoute,
  "/streaming/kafka": KafkaRoute,
  "/streaming/flink": FlinkRoute,
  "/streaming/producers": ProducersRoute,
  // Phase 5 — Admin / tenancy CRUD
  "/admin/orgs": OrgsAdminRoute,
  "/admin/teams": TeamsAdminRoute,
  "/admin/users": UsersAdminRoute,
  "/admin/workspaces": WorkspacesAdminRoute,
  "/admin/projects": ProjectsAdminRoute,
  "/admin/labs": LabsAdminRoute,
  "/admin/configs": LayeredConfigsRoute,
  "/explorer": ResourceExplorerRoute,
  "/models": ModelsProvidersRoute,
  "/settings": SettingsRoute,
  // Phase 6 — Specialty
  "/options/lab": OptionsLabRoute,
  "/monte-carlo": MonteCarloRoute,
  "/optimizer": OptimizerRoute,
  "/docs": DocsRoute,
};

/**
 * Dynamic routes — not present in `NAV_ITEMS` because they take
 * URL parameters, but resolved through the same AppShell.
 */
const DYNAMIC_ROUTES: RouteObject[] = [
  { path: "bots/builder", element: <BotBuilderRoute /> },
  { path: "bots/:id", element: <BotDetailRoute /> },
  { path: "agents/runs/:id", element: <AgentRunDetailRoute /> },
  { path: "backtest/:id", element: <BacktestDetailRoute /> },
  { path: "backtest/new", element: <BacktestNewRoute /> },
  { path: "rl/runs/:id", element: <RlRunDetailRoute /> },
  // Phase 3 dynamic routes.
  { path: "strategies/:id", element: <StrategyDetailRoute /> },
  { path: "data/catalog/:namespace/:name", element: <DataCatalogTableDetailRoute /> },
  // B1 — agent deep links.
  { path: "agents/research/equity", element: <ResearchEquityAgentRoute /> },
  { path: "agents/research/news", element: <ResearchNewsAgentRoute /> },
  { path: "agents/research/universe", element: <ResearchUniverseAgentRoute /> },
  { path: "agents/analysis/step", element: <AnalysisStepAgentRoute /> },
  { path: "agents/analysis/run", element: <AnalysisRunAgentRoute /> },
  { path: "agents/analysis/portfolio", element: <AnalysisPortfolioAgentRoute /> },
  // B3 — Alpha Vantage category routes (deep-linked via dashboard tiles).
  { path: "alpha-vantage/admin", element: <AlphaVantageAdminRoute /> },
  { path: "alpha-vantage/timeseries", element: <AlphaVantageTimeseriesRoute /> },
  { path: "alpha-vantage/fundamentals", element: <AlphaVantageFundamentalsRoute /> },
  { path: "alpha-vantage/technicals", element: <AlphaVantageTechnicalsRoute /> },
  { path: "alpha-vantage/intelligence", element: <AlphaVantageIntelligenceRoute /> },
  { path: "alpha-vantage/forex", element: <AlphaVantageForexRoute /> },
  { path: "alpha-vantage/crypto", element: <AlphaVantageCryptoRoute /> },
  { path: "alpha-vantage/options", element: <AlphaVantageOptionsRoute /> },
  { path: "alpha-vantage/commodities", element: <AlphaVantageCommoditiesRoute /> },
  { path: "alpha-vantage/economics", element: <AlphaVantageEconomicsRoute /> },
  { path: "alpha-vantage/indices", element: <AlphaVantageIndicesRoute /> },
  // B4a — symbol detail (deep link).
  { path: "data/browser/:vt_symbol", element: <DataSymbolBrowserRoute /> },
  // B4c — heavy data deep links.
  { path: "data/datahub", element: <DataDatahubRoute /> },
  { path: "data/engine", element: <DataEngineRoute /> },
  { path: "data/engine/:id", element: <DataEngineDetailRoute /> },
  { path: "data/iceberg/consolidate", element: <IcebergConsolidateRoute /> },
  // B6 — research deep link.
  { path: "research/equity/:symbol", element: <ResearchEquityRoute /> },
  // B7 — streaming detail + strategies/new.
  { path: "streaming/kafka/topics/:name", element: <KafkaTopicDetailRoute /> },
  { path: "streaming/flink/jobs/:name", element: <FlinkJobDetailRoute /> },
  { path: "streaming/producers/:name", element: <ProducerDetailRoute /> },
  { path: "strategies/new", element: <StrategyNewRoute /> },
  // B5 — RL deep links.
  { path: "rl/runs", element: <RlRunsRoute /> },
  { path: "rl/runs/:id/replay", element: <RlReplayRoute /> },
  { path: "rl/library", element: <RlLibraryRoute /> },
  { path: "rl/builder/agent", element: <RlAgentBuilderRoute /> },
  { path: "rl/builder/experiment", element: <RlExperimentBuilderRoute /> },
  { path: "rl/builder/observation", element: <RlObservationBuilderRoute /> },
  { path: "rl/builder/reward", element: <RlRewardBuilderRoute /> },
];

const childRoutes: RouteObject[] = NAV_ITEMS.map((item) => {
  const Component = REAL_ROUTES[item.href];
  const element = Component ? <Component /> : stubRoute(item);
  if (item.href === "/") {
    return { index: true, element } satisfies RouteObject;
  }
  return {
    path: item.href.replace(/^\//, ""),
    element,
  } satisfies RouteObject;
});

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    errorElement: <NotFoundRoute />,
    children: [
      ...childRoutes,
      ...DYNAMIC_ROUTES,
      {
        path: "*",
        element: <NotFoundRoute />,
      },
    ],
  },
]);
