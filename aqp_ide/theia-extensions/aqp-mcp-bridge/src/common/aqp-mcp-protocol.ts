/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

/**
 * Stable command ids for the MCP bridge. Mirrors the
 * `theia-ide-aqp-ext`'s `AqpCommandIds` namespace convention.
 */
export namespace AqpMcpCommandIds {
    export const RECONNECT_ALL = 'aqp.mcp.reconnectAll';
    export const SHOW_STATUS = 'aqp.mcp.showStatus';
}

/**
 * Canonical names registered with the Theia AI MCP server manager. The
 * Research Copilot looks these up by name to enumerate available tools, so
 * any change here is a cross-extension breaking change — coordinate with
 * `theia-ide-aqp-research-copilot-ext`.
 */
export const AQP_MCP_SERVER_NAMES = Object.freeze({
    DATA: 'aqp-data-mcp',
    CODEBASE: 'aqp-codebase-mcp',
});

/**
 * Slot in `AqpRuntimeConfig.mcp` produced by the Theia backend's
 * `GET /aqp/config` endpoint (extended in workstream A-wiring).
 *
 * `url` is the streamable HTTP endpoint of the MCP server (e.g.
 * `https://api.aqp.fund/mcp/data`). `audience` is the canonical URI that
 * the MCP server publishes via its RFC 9728 Protected Resource Metadata
 * document — the access token we mint MUST carry this as its `aud`
 * claim (rule 49).
 */
export interface AqpMcpServerConfig {
    readonly url: string;
    readonly audience: string;
}
