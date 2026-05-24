/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { AQP_MCP_SERVER_NAMES, AqpMcpServerConfig } from '../../common/aqp-mcp-protocol';

/**
 * Per-AQP-MCP-surface registration shape. Stays an in-process type because
 * `@theia/ai-mcp`'s `MCPServerDescription` is the cross-package wire shape
 * and lives in `@theia/ai-mcp/lib/common/mcp-server-manager`.
 *
 * Two AQP MCP surfaces exist today (DataMCP + CodebaseMCP). Future surfaces
 * (e.g. a hypothetical research-papers MCP) just add another entry to
 * `AQP_MCP_SURFACES` below; the registrar iterates over the list.
 */
export interface AqpMcpSurface {
    readonly name: string;
    readonly description: string;
    readonly cfgKey: 'data' | 'codebase';
}

export const AQP_MCP_SURFACES: readonly AqpMcpSurface[] = Object.freeze([
    {
        name: AQP_MCP_SERVER_NAMES.DATA,
        description: 'AQP Data MCP — catalog, datasets, lineage, kubernetes, terraform, agents, ownership, oauth, vector.',
        cfgKey: 'data',
    },
    {
        name: AQP_MCP_SERVER_NAMES.CODEBASE,
        description: 'AQP Codebase MCP — search, find_definition, find_references, get_repo_graph, elaborate_finding.',
        cfgKey: 'codebase',
    },
]);

/**
 * Builds the headers attached to every MCP request for a given surface.
 * The bearer token is injected at call time by the registrar (it is per-
 * surface and short-lived) — this helper only renders the deterministic
 * non-secret headers.
 */
export function staticHeadersFor(
    extensionVersion: string,
    tenancy: Record<string, string>,
): Record<string, string> {
    const headers: Record<string, string> = {
        'Accept': 'application/json, text/event-stream',
        'User-Agent': `AQP-IDE/${extensionVersion} (theia-ide-aqp-mcp-bridge-ext)`,
    };
    for (const [k, v] of Object.entries(tenancy)) {
        headers[k] = v;
    }
    return headers;
}

export function describeSurfaceConfig(cfg: AqpMcpServerConfig | undefined): string {
    if (!cfg) {
        return '(not configured)';
    }
    if (!cfg.url) {
        return '(missing url)';
    }
    if (!cfg.audience) {
        return '(missing audience)';
    }
    return cfg.url;
}
