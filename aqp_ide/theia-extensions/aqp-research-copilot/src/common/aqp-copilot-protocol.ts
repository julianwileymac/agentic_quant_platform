/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

/**
 * Stable identifiers for the AQP Research Copilot. Mirrors the
 * `theia-ide-aqp-ext::AqpCommandIds` convention so a future flat
 * "AQP everything" registry is trivial to assemble.
 */
export namespace AqpCopilotIds {
    /** Theia AI agent id — appears in the AI Configuration view. */
    export const AGENT_ID = 'aqp-research-copilot';

    /** Theia AI language-model id registered by this extension. */
    export const LANGUAGE_MODEL_ID = 'aqp-router-complete';

    /** Prompt fragment ids registered with Theia AI's prompt service. */
    export const PROMPT_SPEC_AUTHORING = 'aqp.copilot.prompts.spec-authoring';
    export const PROMPT_FACTOR_RESEARCH = 'aqp.copilot.prompts.factor-research';
    export const PROMPT_CODEBASE_NAVIGATION = 'aqp.copilot.prompts.codebase-navigation';
}

/**
 * AQP `router_complete` request shape. Mirrors the AQP backend's
 * `aqp.llm.providers.router.RouterCompleteRequest` Pydantic model.
 *
 * `messages` is OpenAI-style chat completions; `model_alias` resolves
 * via AQP's provider catalog (rule 2) — examples: `gpt-4o`, `claude-3-7`,
 * `sera` (when AQP_SERA_ENABLED=true), `ollama:llama3.1:70b`.
 */
export interface RouterCompleteRequest {
    readonly model_alias: string;
    readonly messages: Array<{
        readonly role: 'system' | 'user' | 'assistant' | 'tool';
        readonly content: string;
        readonly name?: string;
        readonly tool_call_id?: string;
    }>;
    readonly tools?: Array<{
        readonly type: 'function';
        readonly function: {
            readonly name: string;
            readonly description: string;
            readonly parameters: object;
        };
    }>;
    readonly temperature?: number;
    readonly max_tokens?: number;
    readonly stream?: boolean;
}

export interface RouterCompleteResponse {
    readonly id: string;
    readonly model: string;
    readonly content: string;
    readonly tool_calls?: Array<{
        readonly id: string;
        readonly type: 'function';
        readonly function: {
            readonly name: string;
            readonly arguments: string;
        };
    }>;
    readonly usage?: {
        readonly prompt_tokens: number;
        readonly completion_tokens: number;
        readonly total_tokens: number;
    };
}
