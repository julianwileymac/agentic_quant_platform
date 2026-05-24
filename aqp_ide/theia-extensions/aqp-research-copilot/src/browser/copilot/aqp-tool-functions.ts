/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { inject, injectable } from '@theia/core/shared/inversify';

import { AqpApiService } from 'theia-ide-aqp-ext/lib/browser/aqp/aqp-api-service';

/**
 * Tool descriptor as understood by Theia AI's `ToolProvider` interface and
 * by AQP's `router_complete` shape. Both follow OpenAI's function-calling
 * convention so the same descriptor works on both ends.
 */
export interface AqpToolDescriptor {
    readonly name: string;
    readonly description: string;
    readonly parameters: object;
    handler(args: Record<string, unknown>): Promise<unknown>;
}

/**
 * Curated tool registry for the AQP Research Copilot. Each entry wraps a
 * single AQP REST endpoint or composite read so the LLM can drive AQP
 * primitives without leaving the chat panel.
 *
 * Hard-rule contract:
 *  - Read tools are safe to expose unconditionally.
 *  - Write tools (anything that creates / runs / halts / mutates) carry
 *    `requiresStepUp: true`; the agent must surface a confirmation chip
 *    before invoking them and propagate the browser's step-up token
 *    (AQP rule 52).
 *  - No tool ever logs or returns secret material (bearer tokens, API
 *    keys, broker credentials) — see `.cursor/rules/aqp-management-engine.mdc`.
 */
@injectable()
export class AqpToolRegistry {

    @inject(AqpApiService)
    protected readonly api!: AqpApiService;

    list(): AqpToolDescriptor[] {
        return [
            // ---- Agent runtime (rules 12-13) -------------------------------
            {
                name: 'aqp.spec.list_agent_specs',
                description: 'List every registered AgentSpec name + version.',
                parameters: { type: 'object', properties: {} },
                handler: () => this.api.get('/agents/specs'),
            },
            {
                name: 'aqp.runs.recent_agent_runs',
                description: 'List the 20 most recent agent runs (rule 13 immutable ledger).',
                parameters: { type: 'object', properties: { limit: { type: 'integer', minimum: 1, maximum: 50 } } },
                handler: args => {
                    const limit = Number(args.limit ?? 20);
                    return this.api.get(`/agents/runs/v2?limit=${limit}`);
                },
            },

            // ---- Workflow runtime (rules 40-41) ----------------------------
            {
                name: 'aqp.spec.list_workflows',
                description: 'List every registered WorkflowSpec.',
                parameters: { type: 'object', properties: {} },
                handler: () => this.api.get('/workflows'),
            },

            // ---- Bot runtime (rules 14-15) ---------------------------------
            {
                name: 'aqp.spec.list_bots',
                description: 'List every registered Bot (TradingBot or ResearchBot).',
                parameters: { type: 'object', properties: {} },
                handler: () => this.api.get('/bots'),
            },

            // ---- RL runtime (rules 16-19, 36-38) ---------------------------
            {
                name: 'aqp.spec.list_rl_experiments',
                description: 'List every registered RLExperimentSpec.',
                parameters: { type: 'object', properties: {} },
                handler: () => this.api.get('/rl/experiments'),
            },
            {
                name: 'aqp.runs.recent_rl_runs',
                description: 'List the 20 most recent RL runs.',
                parameters: { type: 'object', properties: { limit: { type: 'integer', minimum: 1, maximum: 50 } } },
                handler: args => {
                    const limit = Number(args.limit ?? 20);
                    return this.api.get(`/rl/runs?limit=${limit}`);
                },
            },

            // ---- Analysis runtime (rules 23-25) ----------------------------
            {
                name: 'aqp.spec.list_analysis_flows',
                description: 'List every registered AnalysisSpec flow.',
                parameters: { type: 'object', properties: {} },
                handler: () => this.api.get('/analysis/flows'),
            },

            // ---- Backtest engines (the 9 dispatchers) ----------------------
            {
                name: 'aqp.backtest.list_engines',
                description: 'List every registered backtest engine and its EngineCapabilities.',
                parameters: { type: 'object', properties: {} },
                handler: () => this.api.get('/backtest/engines'),
            },

            // ---- Agent health watchdog (rule 5 + agent-watchdog) ----------
            {
                name: 'aqp.health.agent_runs',
                description: 'Snapshot agent_runs_v2 health — counts by status + stalled candidates.',
                parameters: { type: 'object', properties: {} },
                handler: () => this.api.get('/agents/health'),
            },

            // ---- Topology + management (rule 47) ---------------------------
            {
                name: 'aqp.topology.snapshot',
                description: 'Read the topology snapshot (services, clusters, regions).',
                parameters: { type: 'object', properties: {} },
                handler: () => this.api.get('/manage/topology/services'),
            },
        ];
    }
}
