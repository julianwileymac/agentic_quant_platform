/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

/**
 * Stable identifiers for the AQP notebook quant extension. Shared between
 * browser and Node so the renderer + scaffolder + Python helpers agree on
 * the wire surface.
 */

/**
 * The AQP-flavoured MIME type the Perspective Arrow renderer claims.
 * Python kernels emit Arrow record batches under this MIME via
 * `aqp.notebook.helpers.perspective(table)`; Theia routes them here.
 */
export const AQP_PERSPECTIVE_ARROW_MIME = 'application/vnd.aqp.perspective-arrow+arrow';

/** Renderer id passed to Theia's notebook renderer registry. */
export const AQP_PERSPECTIVE_ARROW_RENDERER_ID = 'aqp-perspective-arrow';

/** Command ids surfaced by the notebook scaffolder. */
export namespace AqpNotebookCommandIds {
    export const NEW_AQP_NOTEBOOK = 'aqp.notebook.new';
    export const SHOW_NOTEBOOK_DOCS = 'aqp.notebook.showDocs';
}

/**
 * Default first-cell content for a freshly-scaffolded AQP notebook. Kept
 * here (not in the scaffolder) so unit tests can pin the snapshot.
 *
 * The helper module path (`aqp.notebook.helpers`) is referenced as a
 * string — the kernel imports it at runtime; no TypeScript dependency on
 * `agentic_quant_platform` source is introduced.
 */
export const AQP_NOTEBOOK_HELPER_CELL = [
    '# AQP notebook scaffolded by theia-ide-aqp-notebook-quant-ext.',
    '# The aqp.notebook.helpers module attaches the active AQP tenancy and',
    '# returns ergonomic clients for DataMCP, CodebaseMCP, Arrow Flight, and',
    '# the AQP REST API. Secrets resolve through CredentialResolver (AQP rule 26).',
    'from aqp.notebook.helpers import attach',
    '',
    'ctx = attach()',
    'data = ctx.data           # DataMCP-backed catalog client',
    'codebase = ctx.codebase   # CodebaseMCP-backed search/navigation client',
    'router = ctx.router       # AQP router_complete LLM gateway (rule 2)',
    '',
    "print('AQP notebook attached to', ctx.tenancy_summary())",
    '',
].join('\n');
