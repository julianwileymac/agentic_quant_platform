/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { Emitter, Event, ILogger } from '@theia/core';
import {
    FrontendApplication,
    FrontendApplicationContribution,
} from '@theia/core/lib/browser';
import { inject, injectable, optional } from '@theia/core/shared/inversify';

import { Auth0Service } from 'theia-ide-aqp-ext/lib/browser/auth/auth0-service';
import { AqpConfigService } from 'theia-ide-aqp-ext/lib/browser/aqp/aqp-config-service';
import { AqpTenancyStore } from 'theia-ide-aqp-ext/lib/browser/aqp/aqp-tenancy-store';

import { AQP_MCP_SURFACES, AqpMcpSurface, staticHeadersFor } from './aqp-mcp-server-spec';
import { AqpMcpServerConfig } from '../../common/aqp-mcp-protocol';

/**
 * Theia 1.65+ exposes the MCP server manager from `@theia/ai-mcp/lib/common`.
 * We re-declare the subset of its surface we depend on so this extension's
 * type-check survives minor upstream renames; the manager itself is
 * resolved via `@inject(MCPServerManager)` at runtime.
 *
 * The shape mirrors the public class in
 * https://github.com/eclipse-theia/theia/blob/master/packages/ai-mcp/src/common/mcp-server-manager.ts.
 */
export interface MCPServerDescriptionLike {
    readonly name: string;
    readonly serverUrl?: string;
    readonly serverUrlHeaders?: Record<string, string>;
    readonly autostart?: boolean;
    readonly transport?: 'http' | 'sse' | 'stdio';
    readonly description?: string;
}

export interface MCPServerManagerLike {
    addOrUpdateServer(description: MCPServerDescriptionLike): Promise<void> | void;
    removeServer?(name: string): Promise<void> | void;
    connectServer?(name: string): Promise<void> | void;
}

export const MCPServerManager = Symbol('MCPServerManager');

export interface AqpMcpRegistrationStatus {
    readonly name: string;
    readonly url: string;
    readonly audience: string;
    readonly ok: boolean;
    readonly error?: string;
    readonly lastRegisteredAt?: number;
}

/**
 * Registers AQP's DataMCP + CodebaseMCP servers with Theia AI's MCP client
 * on startup and whenever the user signs in / changes tenancy.
 *
 * Behaviour:
 *  - On `onStart()` we fetch the runtime config, then wait for Auth0 to
 *    finish bootstrap.
 *  - If a config slot is missing or empty, we skip that surface and log a
 *    structured warning (no token leakage — only URL + audience).
 *  - If the user is unauthenticated, we register the server with an empty
 *    bearer (Theia AI's MCP UI will then prompt to retry once the user is
 *    signed in).
 *  - On every Auth0 state change OR tenancy change, we re-register both
 *    surfaces with the freshly-minted tokens + headers.
 *  - `reconnect()` is exposed for the explicit "AQP: MCP — Reconnect All"
 *    command.
 *
 * Tokens never appear in log lines. The 4-character redaction rule
 * (`.cursor/rules/aqp-management-engine.mdc`) applies here.
 */
@injectable()
export class AqpMcpRegistrar implements FrontendApplicationContribution {

    @inject(AqpConfigService)
    protected readonly cfg!: AqpConfigService;

    @inject(Auth0Service)
    protected readonly auth!: Auth0Service;

    @inject(AqpTenancyStore)
    protected readonly tenancy!: AqpTenancyStore;

    @inject(ILogger)
    protected readonly logger!: ILogger;

    // `@theia/ai-mcp`'s MCPServerManager. Marked @optional() so a build
    // configuration that intentionally strips the MCP package out (e.g. a
    // CLI-only Theia variant) doesn't crash this extension at boot.
    @inject(MCPServerManager) @optional()
    protected readonly serverManager?: MCPServerManagerLike;

    protected status = new Map<string, AqpMcpRegistrationStatus>();
    protected readonly _onStatusChanged = new Emitter<Map<string, AqpMcpRegistrationStatus>>();
    readonly onStatusChanged: Event<Map<string, AqpMcpRegistrationStatus>> = this._onStatusChanged.event;

    async onStart(_app: FrontendApplication): Promise<void> {
        if (!this.serverManager) {
            this.logger.warn('[aqp-mcp-bridge] @theia/ai-mcp MCPServerManager not bound. AQP MCP surfaces will not be registered.');
            return;
        }
        try {
            await this.auth.ready;
            await this.reregisterAll();
        } catch (err) {
            this.logger.error('[aqp-mcp-bridge] Initial MCP registration failed:', err instanceof Error ? err.message : err);
        }
        this.auth.onAuthStateChanged(() => {
            this.reregisterAll().catch(err =>
                this.logger.warn('[aqp-mcp-bridge] Re-register on auth change failed:', err instanceof Error ? err.message : err)
            );
        });
        this.tenancy.onTenancyChanged(() => {
            this.reregisterAll().catch(err =>
                this.logger.warn('[aqp-mcp-bridge] Re-register on tenancy change failed:', err instanceof Error ? err.message : err)
            );
        });
    }

    /** Public entry point for the `AQP: MCP — Reconnect All` command. */
    async reconnect(): Promise<void> {
        await this.cfg.reload();
        await this.reregisterAll();
    }

    /** Snapshot of last-known registration state for the status command. */
    getStatus(): ReadonlyMap<string, AqpMcpRegistrationStatus> {
        return this.status;
    }

    protected async reregisterAll(): Promise<void> {
        if (!this.serverManager) {
            return;
        }
        const cfg = await this.cfg.load();
        const mcp = (cfg as { mcp?: Record<string, AqpMcpServerConfig> }).mcp;
        for (const surface of AQP_MCP_SURFACES) {
            const slot = mcp?.[surface.cfgKey];
            await this.registerSurface(surface, slot);
        }
        this._onStatusChanged.fire(new Map(this.status));
    }

    protected async registerSurface(
        surface: AqpMcpSurface,
        slot: AqpMcpServerConfig | undefined,
    ): Promise<void> {
        const url = slot?.url ?? '';
        const audience = slot?.audience ?? '';
        if (!url || !audience) {
            this.recordStatus(surface.name, url, audience, false, 'mcp slot not configured');
            return;
        }
        let bearer = '';
        try {
            const token = await this.auth.getAccessToken();
            if (token) {
                bearer = token;
            }
        } catch (err) {
            this.logger.warn(`[aqp-mcp-bridge] getAccessToken for ${surface.name} failed:`, err instanceof Error ? err.message : err);
        }
        const headers: Record<string, string> = {
            ...staticHeadersFor('1.71.100', this.tenancy.headers()),
        };
        if (bearer) {
            headers['Authorization'] = `Bearer ${bearer}`;
        }
        // Rule 49 contract: per-MCP audience. The AQP backend rejects any
        // token whose `aud` does not match its canonical URI. We pass the
        // audience as a non-secret request header so the AQP IDE
        // operator can verify the wiring from the browser devtools.
        headers['X-AQP-MCP-Audience'] = audience;

        const description: MCPServerDescriptionLike = {
            name: surface.name,
            serverUrl: url,
            serverUrlHeaders: headers,
            autostart: true,
            transport: 'http',
            description: surface.description,
        };
        try {
            await this.serverManager!.addOrUpdateServer(description);
            this.recordStatus(surface.name, url, audience, true);
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this.recordStatus(surface.name, url, audience, false, message);
            this.logger.warn(`[aqp-mcp-bridge] addOrUpdateServer(${surface.name}) failed: ${message}`);
        }
    }

    protected recordStatus(
        name: string,
        url: string,
        audience: string,
        ok: boolean,
        error?: string,
    ): void {
        this.status.set(name, {
            name,
            url,
            audience,
            ok,
            error,
            lastRegisteredAt: ok ? Date.now() : this.status.get(name)?.lastRegisteredAt,
        });
    }
}
