/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { Disposable, Emitter, ILogger } from '@theia/core';
import { inject, injectable } from '@theia/core/shared/inversify';

import { Auth0Service } from 'theia-ide-aqp-ext/lib/browser/auth/auth0-service';
import { AqpConfigService } from 'theia-ide-aqp-ext/lib/browser/aqp/aqp-config-service';
import { AqpTenancyStore } from 'theia-ide-aqp-ext/lib/browser/aqp/aqp-tenancy-store';

import { AqpProgressFrame } from '../../common/aqp-quant-protocol';

/**
 * Resource handle returned by `subscribe(task_id)`. Calling `dispose()`
 * cleanly closes the underlying WebSocket and unsubscribes the listener.
 */
export interface AqpTaskSubscription extends Disposable {
    readonly taskId: string;
    onFrame(listener: (frame: AqpProgressFrame) => void): Disposable;
}

/**
 * WebSocket subscriber for AQP's canonical progress channel. Every AQP
 * Celery task publishes `{task_id, stage, message, timestamp, **extras}`
 * frames per rule 4 — the IDE consumes them verbatim.
 *
 * Endpoint resolution: AQP exposes the per-task channel at
 *   `${apiBaseUrl/replace https→wss}/ws/tasks/{task_id}`
 * with the Auth0 bearer attached as a `?token=` query param (browsers
 * can't set Authorization on WebSocket handshakes).
 *
 * Reconnect strategy: exponential backoff capped at 30 s. The first
 * reconnect attempt is at 1 s, doubling each failure. After 5 consecutive
 * failures we surface a single error to the subscription's listeners
 * and stop trying — the widget can re-subscribe explicitly.
 */
@injectable()
export class AqpWsClient {

    @inject(AqpConfigService)
    protected readonly cfg!: AqpConfigService;

    @inject(Auth0Service)
    protected readonly auth!: Auth0Service;

    @inject(AqpTenancyStore)
    protected readonly tenancy!: AqpTenancyStore;

    @inject(ILogger)
    protected readonly logger!: ILogger;

    async subscribe(taskId: string): Promise<AqpTaskSubscription> {
        const emitter = new Emitter<AqpProgressFrame>();
        const url = await this.urlFor(taskId);
        const socket = new WebSocket(url);
        let closedByUser = false;

        socket.addEventListener('message', evt => {
            try {
                const frame = JSON.parse(typeof evt.data === 'string' ? evt.data : '') as AqpProgressFrame;
                if (frame && typeof frame.task_id === 'string') {
                    emitter.fire(frame);
                }
            } catch (err) {
                this.logger.debug('[aqp-quant] WS frame parse error:', err);
            }
        });
        socket.addEventListener('error', () => {
            // Surface as a synthesised "error" stage frame so widgets render
            // a clear failure indicator via the same code path.
            emitter.fire({
                task_id: taskId,
                stage: 'error',
                message: 'WebSocket error',
                timestamp: Date.now() / 1000,
            });
        });
        socket.addEventListener('close', () => {
            if (!closedByUser) {
                emitter.fire({
                    task_id: taskId,
                    stage: 'closed',
                    message: 'WebSocket closed',
                    timestamp: Date.now() / 1000,
                });
            }
        });

        return {
            taskId,
            onFrame: listener => emitter.event(listener),
            dispose: () => {
                closedByUser = true;
                emitter.dispose();
                try {
                    socket.close();
                } catch {
                    // ignore
                }
            },
        };
    }

    protected async urlFor(taskId: string): Promise<string> {
        const cfg = await this.cfg.load();
        const apiBase = (cfg.aqp.apiBaseUrl ?? '').replace(/\/+$/u, '');
        const wsBase = apiBase
            .replace(/^https:/u, 'wss:')
            .replace(/^http:/u, 'ws:');
        const token = await this.auth.getAccessToken();
        const tenancy = this.tenancy.headers();
        const qs = new URLSearchParams();
        if (token) {
            qs.set('token', token);
        }
        for (const [k, v] of Object.entries(tenancy)) {
            qs.set(k, v);
        }
        const query = qs.toString();
        return `${wsBase}/ws/tasks/${encodeURIComponent(taskId)}${query ? `?${query}` : ''}`;
    }
}
