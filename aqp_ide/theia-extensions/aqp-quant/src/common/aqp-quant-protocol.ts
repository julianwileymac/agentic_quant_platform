/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

/**
 * Stable identifiers, REST paths, and shared types for the AQP quant widgets.
 *
 * The five spec runtimes have a uniform REST surface:
 *
 *   GET  /<runtime>/spec-schema           — JSON schema for the spec form
 *   GET  /<runtime>/specs                 — list of registered spec names + latest version
 *   GET  /<runtime>/specs/{name}          — full spec + version history
 *   POST /<runtime>/specs                 — snapshot (hash-locked; new version row if changed)
 *   POST /<runtime>/runs                  — launch a run; returns a task id
 *   GET  /<runtime>/runs?limit=N          — recent N runs
 *
 * Bots are slightly different (legacy):
 *
 *   GET  /bots                            — list
 *   POST /bots/{ref}/backtest             — launch backtest
 *   POST /bots/{ref}/paper                — launch paper trading
 */

export namespace AqpQuantViewIds {
    export const SPEC_AUTHOR = 'aqp.quant.view.spec-author';
    export const RUN_INSPECTOR = 'aqp.quant.view.run-inspector';
    export const BACKTEST_RUNNER = 'aqp.quant.view.backtest-runner';
}

export namespace AqpQuantCommandIds {
    export const OPEN_SPEC_AUTHOR = 'aqp.quant.openSpecAuthor';
    export const OPEN_RUN_INSPECTOR = 'aqp.quant.openRunInspector';
    export const OPEN_BACKTEST_RUNNER = 'aqp.quant.openBacktestRunner';
    export const ATTACH_RUN = 'aqp.quant.attachRun';
}

/**
 * The five hash-locked spec runtimes. Order matters: it determines the
 * dropdown order in SpecAuthorWidget. Keep this list aligned with
 * `AGENTS.md` hard rules 12-17, 23-25, 40-41.
 */
export const AQP_SPEC_KINDS = Object.freeze([
    {
        kind: 'agent' as const,
        label: 'Agent',
        runtime: 'AgentRuntime',
        immutabilityRule: 'rule 13',
        listPath: '/agents/specs',
        getPath: (name: string): string => `/agents/specs/${encodeURIComponent(name)}`,
        snapshotPath: '/agents/specs',
        schemaPath: '/agents/spec-schema',
        runPath: '/agents/runs/v2',
    },
    {
        kind: 'bot' as const,
        label: 'Bot',
        runtime: 'BotRuntime',
        immutabilityRule: 'rule 15',
        listPath: '/bots',
        getPath: (name: string): string => `/bots/${encodeURIComponent(name)}`,
        snapshotPath: '/bots',
        schemaPath: '/bots/spec-schema',
        runPath: '/bots/runs',
    },
    {
        kind: 'rl' as const,
        label: 'RL Experiment',
        runtime: 'RLRuntime',
        immutabilityRule: 'rule 17',
        listPath: '/rl/experiments',
        getPath: (name: string): string => `/rl/experiments/${encodeURIComponent(name)}`,
        snapshotPath: '/rl/experiments',
        schemaPath: '/rl/spec-schema',
        runPath: '/rl/runs',
    },
    {
        kind: 'analysis' as const,
        label: 'Analysis',
        runtime: 'AnalysisRuntime',
        immutabilityRule: 'rule 24',
        listPath: '/analysis/specs',
        getPath: (name: string): string => `/analysis/specs/${encodeURIComponent(name)}`,
        snapshotPath: '/analysis/specs',
        schemaPath: '/analysis/spec-schema',
        runPath: '/analysis/runs',
    },
    {
        kind: 'workflow' as const,
        label: 'Workflow',
        runtime: 'WorkflowRuntime',
        immutabilityRule: 'rule 41',
        listPath: '/workflows',
        getPath: (name: string): string => `/workflows/${encodeURIComponent(name)}`,
        snapshotPath: '/workflows',
        schemaPath: '/workflows/spec-schema',
        runPath: '/workflows/runs',
    },
]);

export type AqpSpecKind = (typeof AQP_SPEC_KINDS)[number]['kind'];

/**
 * The canonical AQP progress frame (rule 4). Backend tasks publish these
 * frames to the Redis pub/sub channel via `aqp.tasks._progress.emit`; the
 * Theia WebSocket subscriber receives them verbatim.
 *
 * `extras` is intentionally open-ended — each task family adds its own
 * keys (e.g. an RL run adds `step`, `episode`, `mean_reward`).
 */
export interface AqpProgressFrame {
    readonly task_id: string;
    readonly stage: string;
    readonly message: string;
    readonly timestamp: number | string;
    readonly [extras: string]: unknown;
}

/**
 * Minimal summary returned by `GET /<runtime>/specs` list endpoints. The
 * SpecAuthorWidget's dropdown only needs name + latest version; the full
 * spec body comes from `GET /<runtime>/specs/{name}`.
 */
export interface AqpSpecSummary {
    readonly name: string;
    readonly version?: number | string;
    readonly created_at?: string;
    readonly hash?: string;
}
