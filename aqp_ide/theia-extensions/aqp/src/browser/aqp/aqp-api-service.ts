/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { ILogger } from '@theia/core/lib/common';
import { inject, injectable } from '@theia/core/shared/inversify';

import { Auth0Service } from '../auth/auth0-service';
import { AqpConfigService } from './aqp-config-service';
import { AqpTenancyStore } from './aqp-tenancy-store';

export class AqpHttpError extends Error {
    constructor(
        readonly status: number,
        readonly statusText: string,
        readonly body: string,
        readonly url: string,
    ) {
        super(`AQP HTTP ${status} ${statusText} for ${url}: ${body || '(no body)'}`);
        this.name = 'AqpHttpError';
    }
}

/**
 * Authenticated HTTP client for the AQP FastAPI. Mirrors the
 * `frontend/src/lib/api/client.ts::apiFetch` shape in the AQP Vite
 * frontend so backend route expectations stay in lockstep:
 *
 *  - `Authorization: Bearer <auth0-access-token>` (auto-refreshed via Auth0Service)
 *  - `X-AQP-Workspace`, `X-AQP-Project`, `X-AQP-Lab`, `X-AQP-Org`, `X-AQP-Team`
 *    headers from AqpTenancyStore (only the ones the user has set)
 *  - JSON Content-Type + Accept by default
 *  - Throws AqpHttpError on non-2xx, returns parsed JSON otherwise.
 *
 * Token attachment is best-effort - if Auth0Service can't refresh silently
 * (user logged out), we still send the request but without the Authorization
 * header, so AQP responds 401 and widgets can prompt for login.
 */
@injectable()
export class AqpApiService {

    @inject(Auth0Service)
    protected readonly auth: Auth0Service;

    @inject(AqpConfigService)
    protected readonly cfg: AqpConfigService;

    @inject(AqpTenancyStore)
    protected readonly tenancy: AqpTenancyStore;

    @inject(ILogger)
    protected readonly logger: ILogger;

    async get<T = unknown>(path: string): Promise<T> {
        return this.request<T>('GET', path);
    }

    async post<T = unknown>(path: string, body?: unknown): Promise<T> {
        return this.request<T>('POST', path, body);
    }

    async put<T = unknown>(path: string, body?: unknown): Promise<T> {
        return this.request<T>('PUT', path, body);
    }

    async del<T = unknown>(path: string): Promise<T> {
        return this.request<T>('DELETE', path);
    }

    /**
     * Convenience helper for `POST` to one of the AQP halt endpoints. Mirrors
     * the AQP frontend KillSwitch fan-out: best-effort, never raises, returns
     * `{ ok, status, body }` so the caller can render per-endpoint outcomes.
     */
    async safePost(path: string, body?: unknown): Promise<{ ok: boolean; status: number; body: string }> {
        try {
            const res = await this.rawFetch('POST', path, body);
            const text = await res.text();
            return { ok: res.ok, status: res.status, body: text };
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            return { ok: false, status: 0, body: message };
        }
    }

    protected async request<T>(method: string, path: string, body?: unknown): Promise<T> {
        const res = await this.rawFetch(method, path, body);
        const text = await res.text();
        if (!res.ok) {
            throw new AqpHttpError(res.status, res.statusText, text, res.url);
        }
        if (res.status === 204 || !text) {
            return undefined as unknown as T;
        }
        try {
            return JSON.parse(text) as T;
        } catch (err) {
            // Some AQP endpoints (e.g. log tails) return text/plain. Surface
            // the raw text as a string-typed T rather than crashing.
            return text as unknown as T;
        }
    }

    protected async rawFetch(method: string, path: string, body: unknown): Promise<Response> {
        const cfg = await this.cfg.load();
        const baseUrl = (cfg.aqp.apiBaseUrl ?? '').replace(/\/+$/, '');
        if (!baseUrl) {
            throw new Error('AQP API base URL is not configured. Set AQP_THEIA_API_URL.');
        }
        const url = `${baseUrl}${path.startsWith('/') ? path : `/${path}`}`;

        const headers = new Headers();
        headers.set('Accept', 'application/json');
        if (body !== undefined) {
            headers.set('Content-Type', 'application/json');
        }
        const token = await this.auth.getAccessToken();
        if (token) {
            headers.set('Authorization', `Bearer ${token}`);
        }
        for (const [k, v] of Object.entries(this.tenancy.headers())) {
            headers.set(k, v);
        }

        return fetch(url, {
            method,
            headers,
            body: body !== undefined ? JSON.stringify(body) : undefined,
            credentials: 'omit',
        });
    }
}
