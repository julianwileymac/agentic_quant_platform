/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

/**
 * Shared constants used by both the Theia frontend (browser bundle) and the
 * Theia Node backend. Values that need to stay in lockstep (command ids, view
 * ids, the kill-switch endpoint list, tenancy header names) live here.
 */

export const AQP_EXTENSION_ID = 'theia-aqp-ext';

export namespace AqpCommandIds {
    export const LOGIN = 'aqp.login';
    export const LOGOUT = 'aqp.logout';
    export const HALT_ALL = 'aqp.haltAll';
    export const OPEN_AGENTS = 'aqp.openAgents';
    export const OPEN_WORKFLOWS = 'aqp.openWorkflows';
    export const OPEN_BOTS = 'aqp.openBots';
    export const OPEN_TOPOLOGY = 'aqp.openTopology';
    // Management Engine widget (Phase F of aqp_management_engine plan).
    export const OPEN_MANAGEMENT = 'aqp.openManagement';
    export const SET_TENANCY = 'aqp.setTenancy';
}

export namespace AqpViewIds {
    export const AGENT_RUNS = 'aqp.view.agentRuns';
    export const WORKFLOWS = 'aqp.view.workflows';
    export const BOTS = 'aqp.view.bots';
    export const TOPOLOGY = 'aqp.view.topology';
    // Management Engine (Phase F of aqp_management_engine plan).
    export const MANAGEMENT = 'aqp.view.management';
}

/**
 * Endpoints fanned out by the global `aqp.haltAll` command. Mirrors the
 * KillSwitch component in the AQP Vite frontend (rules 40-42 + Don't list).
 * Any new long-running runtime added on the AQP side should be appended here.
 */
export const KILL_SWITCH_ENDPOINTS: readonly string[] = [
    '/agents/halt',
    '/paper/stop-all',
    '/bots/halt-all',
    '/rl/halt-all',
    '/quant-agents/halt',
    '/workflows/halt',
    '/terraform/halt',
    '/assistants/halt',
    // Management Engine (Phase B of aqp_management_engine plan).
    '/workloads/halt',
];

/**
 * Tenancy headers consumed by `aqp/auth/deps.py::current_context` on the
 * AQP backend. `AqpApiService` attaches whichever ones the user has set.
 */
export namespace TenancyHeaders {
    export const WORKSPACE = 'X-AQP-Workspace';
    export const PROJECT = 'X-AQP-Project';
    export const LAB = 'X-AQP-Lab';
    export const ORG = 'X-AQP-Org';
    export const TEAM = 'X-AQP-Team';
}

/**
 * Per-MCP-surface configuration shape. The AQP backend serves these via
 * `GET /aqp/config` so the `theia-ide-aqp-mcp-bridge-ext` extension can
 * pre-register the MCP servers with the bundled `@theia/ai-mcp` client.
 *
 * - `url` is the streamable HTTP endpoint of the MCP server
 *   (e.g. `https://api.aqp.fund/mcp/data`).
 * - `audience` is the canonical URI advertised by the MCP server's
 *   RFC 9728 Protected Resource Metadata document. The access token
 *   we mint MUST carry this as its `aud` claim (AQP rule 49 — no
 *   token passthrough across audiences).
 */
export interface AqpMcpConfigSlot {
    url: string;
    audience: string;
}

export interface AqpRuntimeConfig {
    auth0: {
        domain: string;
        clientId: string;
        audience: string;
        scope: string;
        redirectUri: string;
        organization?: string;
    };
    aqp: {
        apiBaseUrl: string;
        // Public origin of the AQP Vite frontend so the Theia
        // ManagementWidget can iframe `/manage`, `/cluster-mgmt`, and
        // `/cloudflare` directly. Falls back to apiBaseUrl when unset.
        frontendUrl?: string;
        // GET path for `/auth/providers` (BFF bootstrap). Defaults to
        // `${apiBaseUrl}/auth/providers`.
        providersUrl?: string;
    };
    /**
     * MCP server configuration consumed by `theia-ide-aqp-mcp-bridge-ext`.
     * Optional so older Theia backends that don't set the env vars degrade
     * gracefully (the bridge skips registration and logs a structured
     * warning rather than crashing).
     */
    mcp?: {
        data?: AqpMcpConfigSlot;
        codebase?: AqpMcpConfigSlot;
    };
    /**
     * Research-copilot configuration. Optional. When `seraEnabled` is true,
     * the copilot defaults to AQP's SERA-32B code model for codebase tools.
     * `routerCompletePath` overrides the default `/llm/router/complete` path.
     */
    copilot?: {
        seraEnabled?: boolean;
        routerCompletePath?: string;
    };
}
