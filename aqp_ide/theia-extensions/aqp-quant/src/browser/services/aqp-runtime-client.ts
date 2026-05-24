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

import {
    AQP_SPEC_KINDS,
    AqpSpecKind,
    AqpSpecSummary,
} from '../../common/aqp-quant-protocol';

/**
 * Typed REST client for the five spec runtimes. Every call routes through
 * `AqpApiService` (Auth0 bearer + tenancy headers + tenant-aware base URL).
 *
 * The methods are intentionally thin — no business logic, no caching, just
 * URL composition + JSON parsing. Higher-level UI logic lives in widgets.
 */
@injectable()
export class AqpRuntimeClient {

    @inject(AqpApiService)
    protected readonly api!: AqpApiService;

    listSpecs(kind: AqpSpecKind): Promise<AqpSpecSummary[]> {
        const cfg = this.cfgFor(kind);
        return this.api.get<AqpSpecSummary[]>(cfg.listPath).catch(() => []);
    }

    getSpec(kind: AqpSpecKind, name: string): Promise<unknown> {
        const cfg = this.cfgFor(kind);
        return this.api.get(cfg.getPath(name));
    }

    getSpecSchema(kind: AqpSpecKind): Promise<unknown> {
        const cfg = this.cfgFor(kind);
        return this.api.get(cfg.schemaPath).catch(() => ({}));
    }

    /**
     * Snapshot a spec. AQP's `persist_spec` is hash-locked (rules 13, 15,
     * 17, 24, 41) — the returned row carries `version` and `hash`.
     */
    snapshotSpec(kind: AqpSpecKind, spec: unknown): Promise<{ version: number | string; hash: string }> {
        const cfg = this.cfgFor(kind);
        return this.api.post(cfg.snapshotPath, spec);
    }

    /**
     * Launch a run for the named spec. Returns the canonical `{ task_id }`
     * envelope used by every AQP runtime; widgets subscribe via
     * `AqpWsClient.subscribe(task_id)`.
     */
    runSpec(kind: AqpSpecKind, name: string, input: unknown): Promise<{ task_id: string }> {
        const cfg = this.cfgFor(kind);
        return this.api.post(cfg.runPath, { spec_name: name, input });
    }

    /** Recent N runs for the given runtime — for RunInspector backfill. */
    recentRuns(kind: AqpSpecKind, limit = 20): Promise<unknown[]> {
        const cfg = this.cfgFor(kind);
        return this.api.get<unknown[]>(`${cfg.runPath}?limit=${limit}`).catch(() => []);
    }

    // --- Bot-specific shortcuts -------------------------------------------

    listBots(): Promise<Array<{ ref: string; kind?: string }>> {
        return this.api.get<Array<{ ref: string; kind?: string }>>('/bots').catch(() => []);
    }

    backtestBot(ref: string, body?: unknown): Promise<{ task_id: string }> {
        return this.api.post(`/bots/${encodeURIComponent(ref)}/backtest`, body ?? {});
    }

    paperBot(ref: string, body?: unknown): Promise<{ task_id: string }> {
        return this.api.post(`/bots/${encodeURIComponent(ref)}/paper`, body ?? {});
    }

    // --- Backtest engine catalog (the 9 dispatchers) ----------------------

    listEngines(): Promise<Array<{ name: string; capabilities?: Record<string, unknown> }>> {
        return this.api
            .get<Array<{ name: string; capabilities?: Record<string, unknown> }>>('/backtest/engines')
            .catch(() => []);
    }

    protected cfgFor(kind: AqpSpecKind): (typeof AQP_SPEC_KINDS)[number] {
        const found = AQP_SPEC_KINDS.find(k => k.kind === kind);
        if (!found) {
            throw new Error(`Unknown AQP spec kind: ${kind}`);
        }
        return found;
    }
}
