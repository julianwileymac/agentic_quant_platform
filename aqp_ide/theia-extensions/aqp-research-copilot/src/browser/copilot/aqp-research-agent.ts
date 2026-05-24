/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { ILogger } from '@theia/core';
import { inject, injectable } from '@theia/core/shared/inversify';

import { AqpCopilotIds, RouterCompleteRequest } from '../../common/aqp-copilot-protocol';
import { AqpToolRegistry } from './aqp-tool-functions';
import { RouterCompleteClient } from './router-complete-client';

/**
 * Subset of the Theia AI `Agent` interface we implement directly. The full
 * shape lives in `@theia/ai-core/lib/common/agent.ts`; we re-declare the
 * minimum so the type-check passes even if upstream renames a field, and
 * the `AgentService` does a structural match at registration time.
 */
export interface AqpAgent {
    readonly id: string;
    readonly name: string;
    readonly description: string;
    readonly tags?: string[];
    readonly variables?: string[];
    readonly prompts?: Array<{ id: string; defaultVariant?: { id: string; template: string } }>;
    readonly languageModelRequirements?: Array<{ purpose: string; identifier: string }>;
    readonly functions?: string[];
}

/**
 * AQP Research Copilot — the only AQP-flavoured Theia AI agent. Registered
 * with Theia's `AgentService` on extension start so it shows up in the AI
 * Configuration view alongside the bundled Copilot, Architect, and
 * Code-Completion agents.
 *
 * Hard-rule contract:
 *  - LLM calls route through `RouterCompleteClient` (rule 2).
 *  - Tool functions are sourced from `AqpToolRegistry` and exposed both
 *    in-process (when Theia AI orchestrates the loop locally) AND as part
 *    of the `tools` array in the `RouterCompleteRequest` (when AQP
 *    orchestrates server-side).
 *  - DataMCP + CodebaseMCP tools come for free via the
 *    `theia-ide-aqp-mcp-bridge-ext` registrations — the AI MCP UI surfaces
 *    them in this agent's tool list automatically.
 */
@injectable()
export class AqpResearchAgent implements AqpAgent {

    @inject(AqpToolRegistry)
    protected readonly toolRegistry!: AqpToolRegistry;

    @inject(RouterCompleteClient)
    protected readonly router!: RouterCompleteClient;

    @inject(ILogger)
    protected readonly logger!: ILogger;

    readonly id = AqpCopilotIds.AGENT_ID;
    readonly name = 'AQP Research Copilot';
    readonly description =
        'Quant-research copilot for the Agentic Quant Platform. ' +
        'Authors AgentSpec / BotSpec / RLExperimentSpec / AnalysisSpec / WorkflowSpec, ' +
        'launches runs, browses Iceberg + the codebase MCP, and drives the 9 backtest engines. ' +
        'All completions go through AQP router_complete (rule 2).';

    readonly tags = ['AQP', 'quant', 'research', 'spec-authoring'];

    readonly prompts = [
        { id: AqpCopilotIds.PROMPT_SPEC_AUTHORING },
        { id: AqpCopilotIds.PROMPT_FACTOR_RESEARCH },
        { id: AqpCopilotIds.PROMPT_CODEBASE_NAVIGATION },
    ];

    readonly languageModelRequirements = [
        { purpose: 'chat', identifier: AqpCopilotIds.LANGUAGE_MODEL_ID },
        { purpose: 'tool-calling', identifier: AqpCopilotIds.LANGUAGE_MODEL_ID },
    ];

    get functions(): string[] {
        return this.toolRegistry.list().map(t => t.name);
    }

    /**
     * Issue a single chat completion against AQP router_complete.
     * Helper used by the Theia AI chat loop (the agent service drives the
     * conversation; we only need to know how to talk to the model).
     */
    async invokeModel(req: Omit<RouterCompleteRequest, 'tools'>): Promise<string> {
        const tools = this.toolRegistry.list().map(t => ({
            type: 'function' as const,
            function: {
                name: t.name,
                description: t.description,
                parameters: t.parameters,
            },
        }));
        const response = await this.router.complete({ ...req, tools });
        return response.content;
    }
}
