/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { Endpoint } from '@theia/core/lib/browser';
import { ILogger } from '@theia/core/lib/common';
import { inject, injectable } from '@theia/core/shared/inversify';

import { AqpRuntimeConfig } from '../../common/aqp-protocol';

/**
 * Fetches AQP + Auth0 runtime config from the Theia backend's
 * `GET /aqp/config` endpoint exactly once, caches the result, and lets
 * every other service `await load()` without re-fetching.
 *
 * Mirrors the Theia "launcher" extension's `Endpoint({ path: 'launcher' })`
 * pattern for same-origin REST.
 */
@injectable()
export class AqpConfigService {

    @inject(ILogger)
    protected readonly logger: ILogger;

    private cached?: AqpRuntimeConfig;
    private inflight?: Promise<AqpRuntimeConfig>;

    async load(): Promise<AqpRuntimeConfig> {
        if (this.cached) {
            return this.cached;
        }
        if (this.inflight) {
            return this.inflight;
        }
        this.inflight = this.fetchConfig().then(cfg => {
            this.cached = cfg;
            this.inflight = undefined;
            return cfg;
        }).catch(err => {
            this.inflight = undefined;
            throw err;
        });
        return this.inflight;
    }

    /** Force-reload the config. Used by the "AQP: Reload Config" command. */
    async reload(): Promise<AqpRuntimeConfig> {
        this.cached = undefined;
        return this.load();
    }

    protected async fetchConfig(): Promise<AqpRuntimeConfig> {
        const url = new Endpoint({ path: 'aqp/config' }).getRestUrl().toString();
        const cleanUrl = url.endsWith('/') ? url.slice(0, -1) : url;
        try {
            const response = await fetch(cleanUrl, {
                method: 'GET',
                headers: { Accept: 'application/json' },
            });
            if (!response.ok) {
                throw new Error(`GET ${cleanUrl} returned HTTP ${response.status}`);
            }
            const parsed = await response.json() as AqpRuntimeConfig;
            return parsed;
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this.logger.error('[aqp-ext] Failed to load AQP runtime config:', message);
            // Return a config shape with empty Auth0 fields so the SDK
            // bootstrap reports a clear "not configured" error instead of
            // crashing the IDE.
            return {
                auth0: {
                    domain: '',
                    clientId: '',
                    audience: '',
                    scope: 'openid profile email offline_access',
                    redirectUri: '',
                },
                aqp: { apiBaseUrl: '' },
            };
        }
    }
}
