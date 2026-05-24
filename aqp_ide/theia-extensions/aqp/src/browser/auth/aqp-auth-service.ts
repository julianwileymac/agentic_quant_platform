/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { Emitter, Event, ILogger } from '@theia/core/lib/common';
import { FrontendApplication, FrontendApplicationContribution } from '@theia/core/lib/browser';
import { inject, injectable } from '@theia/core/shared/inversify';

import { AqpConfigService } from '../aqp/aqp-config-service';

/**
 * AQP Management Engine BFF auth service.
 *
 * This is an ADDITIVE service alongside the existing Auth0Service.
 * It calls the AQP backend's `/auth/providers` endpoint to enumerate
 * every registered IdentityProvider (Auth0 / Entra / Cloudflare
 * Access / Mock) so the management widget can render a provider
 * picker, and it talks to `/auth/refresh` for server-side refresh.
 *
 * Critical differences vs Auth0Service:
 *
 * - NEVER persists tokens to localStorage (the BFF flow keeps refresh
 *   tokens in the encrypted `aqp_session` cookie on the AQP backend).
 * - NEVER decodes tokens client-side; the AQP backend is the trust
 *   boundary for scope / role expansion.
 * - All HTTP calls go through `aqp-api-service`'s `Authorization:
 *   Bearer` injection, so the same access token Auth0Service supplies
 *   today flows through unchanged.
 *
 * The Management Engine subagent rule
 * (`.cursor/rules/aqp-management-engine.mdc` in the AQP repo) forbids
 * logging tokens. This file follows the same convention — error logs
 * NEVER include the inbound or rotated token value.
 */

export interface AqpAuthProviderDescriptor {
    alias: string;
    kind: string;
    issuer?: string | null;
    audience?: string | null;
    has_client_secret?: boolean;
    is_active?: boolean;
}

export interface AqpAuthBootstrap {
    active_provider: string;
    providers: AqpAuthProviderDescriptor[];
    loaded_at: number;
}

const INITIAL_BOOTSTRAP: AqpAuthBootstrap = {
    active_provider: '',
    providers: [],
    loaded_at: 0,
};

@injectable()
export class AqpAuthService implements FrontendApplicationContribution {

    @inject(AqpConfigService)
    protected readonly cfg!: AqpConfigService;

    @inject(ILogger)
    protected readonly logger!: ILogger;

    private bootstrap: AqpAuthBootstrap = INITIAL_BOOTSTRAP;
    private readonly _onChange = new Emitter<AqpAuthBootstrap>();
    readonly onBootstrapChanged: Event<AqpAuthBootstrap> = this._onChange.event;

    private readyResolve?: () => void;
    readonly ready: Promise<void> = new Promise(resolve => { this.readyResolve = resolve; });

    async onStart(_app: FrontendApplication): Promise<void> {
        try {
            await this.refreshBootstrap();
        } catch (err) {
            // Never include the error object directly in case it embeds
            // a token — only the message string.
            const message = err instanceof Error ? err.message : String(err);
            this.logger.warn(`[aqp-ext] AQP auth bootstrap failed: ${message}`);
        } finally {
            this.readyResolve?.();
        }
    }

    /**
     * Fetch GET /auth/providers from the AQP backend.
     * Falls back to an empty bootstrap when the backend is unreachable
     * so widgets can render a "single Auth0 provider" UI from the
     * existing config service.
     */
    async refreshBootstrap(): Promise<AqpAuthBootstrap> {
        const cfg = await this.cfg.load();
        const base = (cfg.aqp?.apiBaseUrl || '').replace(/\/+$/u, '');
        if (!base) {
            this.bootstrap = INITIAL_BOOTSTRAP;
            this._onChange.fire(this.bootstrap);
            return this.bootstrap;
        }
        const url = `${base}/auth/providers`;
        try {
            const res = await fetch(url, {
                method: 'GET',
                credentials: 'include',
                headers: { Accept: 'application/json' },
            });
            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`);
            }
            const body = await res.json();
            this.bootstrap = {
                active_provider: String(body.active_provider || ''),
                providers: Array.isArray(body.providers)
                    ? body.providers.map((p: Record<string, unknown>) => ({
                        alias: String(p.alias ?? ''),
                        kind: String(p.kind ?? ''),
                        issuer: (p.issuer as string | null) ?? null,
                        audience: (p.audience as string | null) ?? null,
                        has_client_secret: Boolean(p.has_client_secret),
                        is_active: Boolean(p.is_active),
                    }))
                    : [],
                loaded_at: Date.now(),
            };
            this._onChange.fire(this.bootstrap);
            return this.bootstrap;
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this.logger.debug(`[aqp-ext] /auth/providers fetch failed: ${message}`);
            this.bootstrap = INITIAL_BOOTSTRAP;
            this._onChange.fire(this.bootstrap);
            return this.bootstrap;
        }
    }

    /**
     * POST /auth/refresh — server-side refresh exchange.
     *
     * The refresh token MUST never be persisted to localStorage; the
     * caller (Auth0Service) holds it in memory and passes it here when
     * the existing silent refresh hits a degraded path (third-party
     * cookies blocked, etc.). Returns the rotated access token + any
     * new refresh token the IdP rotated.
     */
    async refreshAccessToken(refreshToken: string): Promise<{
        access_token: string;
        refresh_token?: string;
        id_token?: string;
        expires_in?: number;
        scope?: string;
    } | null> {
        const cfg = await this.cfg.load();
        const base = (cfg.aqp?.apiBaseUrl || '').replace(/\/+$/u, '');
        if (!base || !refreshToken) return null;
        const url = `${base}/auth/refresh`;
        try {
            const res = await fetch(url, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    Accept: 'application/json',
                    'Content-Type': 'application/json',
                },
                // Refresh token in the body — never logged. Browser
                // network panel sees it during dev, but the AQP backend
                // does not echo it to access logs.
                body: JSON.stringify({ refresh_token: refreshToken }),
            });
            if (!res.ok) {
                this.logger.warn(`[aqp-ext] /auth/refresh failed: HTTP ${res.status}`);
                return null;
            }
            const body = await res.json();
            return {
                access_token: String(body.access_token ?? ''),
                refresh_token: (body.refresh_token as string | undefined) ?? undefined,
                id_token: (body.id_token as string | undefined) ?? undefined,
                expires_in: (body.expires_in as number | undefined) ?? undefined,
                scope: (body.scope as string | undefined) ?? undefined,
            };
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this.logger.warn(`[aqp-ext] /auth/refresh threw: ${message}`);
            return null;
        }
    }

    /** Cheap getter for current bootstrap state (sync). */
    getBootstrap(): AqpAuthBootstrap {
        return this.bootstrap;
    }
}
