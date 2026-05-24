/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

/**
 * Hand-typed minimal shapes of AQP API responses used by the Phase-1 widgets.
 * These intentionally cover only the fields the widgets read - anything
 * richer comes in Phase 2 via openapi-typescript codegen against the AQP
 * `GET /openapi.json` (see plan section 11 - "Out-of-scope").
 *
 * The shapes are taken from the AQP source of truth (`aqp/api/routes/*.py`
 * + `aqp/persistence/models_*.py`) - widen them rather than narrow when
 * the AQP API changes, to keep this client tolerant of optional fields.
 */

export interface AqpAgentSpecSummary {
    name: string;
    description?: string;
    model?: { provider?: string; model?: string };
    version?: string;
    spec_hash?: string;
}

export interface AqpAgentRunResult {
    run_id?: string;
    status?: string;
    output?: unknown;
    error?: string;
    started_at?: string;
    finished_at?: string;
}

export interface AqpAgentRunSummary {
    run_id: string;
    spec_name?: string;
    status?: string;
    created_at?: string;
    finished_at?: string;
}

export interface AqpWorkflowSummary {
    name: string;
    description?: string;
    spec_hash?: string;
    adapter_kind?: string;
}

export interface AqpWorkflowRunSummary {
    run_id: string;
    workflow_name?: string;
    status?: string;
    started_at?: string;
}

export interface AqpBotSummary {
    id: number | string;
    name: string;
    kind?: string;
    status?: string;
    spec_hash?: string;
}

export interface AqpHaltResponse {
    halted?: number;
    status?: string;
    detail?: string;
}

export interface AqpTopologyTarget {
    id: string | number;
    name?: string;
    kind?: string;
    cluster?: string;
    namespace?: string;
    region?: string;
    ready?: boolean;
}

export interface AqpTopologySnapshot {
    generated_at?: string;
    targets: AqpTopologyTarget[];
}

/**
 * Pickable entity shapes used by the `aqp.setTenancy` QuickInput flow.
 * Match the JSON returned by `/orgs`, `/teams`, `/workspaces`, `/projects`,
 * `/labs` - all four share an `id` + display field.
 */
export interface AqpEntityRef {
    id: string | number;
    name?: string;
    slug?: string;
    description?: string;
}
