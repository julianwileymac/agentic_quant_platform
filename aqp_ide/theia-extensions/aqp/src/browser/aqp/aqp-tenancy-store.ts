/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { Emitter, Event, ILogger } from '@theia/core/lib/common';
import { FrontendApplication, FrontendApplicationContribution, StorageService } from '@theia/core/lib/browser';
import { inject, injectable } from '@theia/core/shared/inversify';

import { TenancyHeaders } from '../../common/aqp-protocol';

export interface AqpTenancy {
    org?: string;
    team?: string;
    workspace?: string;
    project?: string;
    lab?: string;
}

const STORAGE_KEY = 'aqp.tenancy.v1';

/**
 * Stores the currently-selected tenancy (org, team, workspace, project,
 * lab) and persists it via @theia/core StorageService so it survives
 * page reload. Values are surfaced to the AQP backend via the
 * `X-AQP-*` headers consumed by `aqp/auth/deps.py::current_context`.
 */
@injectable()
export class AqpTenancyStore implements FrontendApplicationContribution {

    @inject(StorageService)
    protected readonly storage: StorageService;

    @inject(ILogger)
    protected readonly logger: ILogger;

    private state: AqpTenancy = {};
    private readonly _onChange = new Emitter<AqpTenancy>();
    readonly onTenancyChanged: Event<AqpTenancy> = this._onChange.event;

    async onStart(_app: FrontendApplication): Promise<void> {
        try {
            const restored = await this.storage.getData<AqpTenancy>(STORAGE_KEY);
            if (restored && typeof restored === 'object') {
                this.state = { ...restored };
            }
        } catch (err) {
            this.logger.warn('[aqp-ext] Failed to restore tenancy from StorageService:', err);
        }
    }

    get(): AqpTenancy {
        return { ...this.state };
    }

    async set(next: AqpTenancy): Promise<void> {
        this.state = { ...next };
        await this.storage.setData(STORAGE_KEY, this.state);
        this._onChange.fire(this.get());
    }

    async clear(): Promise<void> {
        await this.set({});
    }

    /**
     * Returns the subset of tenancy headers that have a non-empty value.
     * Empty / undefined values are omitted so we don't send blank
     * `X-AQP-Workspace: ` headers (AQP would reject them as malformed).
     */
    headers(): Record<string, string> {
        const out: Record<string, string> = {};
        if (this.state.org) {
            out[TenancyHeaders.ORG] = this.state.org;
        }
        if (this.state.team) {
            out[TenancyHeaders.TEAM] = this.state.team;
        }
        if (this.state.workspace) {
            out[TenancyHeaders.WORKSPACE] = this.state.workspace;
        }
        if (this.state.project) {
            out[TenancyHeaders.PROJECT] = this.state.project;
        }
        if (this.state.lab) {
            out[TenancyHeaders.LAB] = this.state.lab;
        }
        return out;
    }
}
