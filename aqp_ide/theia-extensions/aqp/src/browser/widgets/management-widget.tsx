/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import * as React from '@theia/core/shared/react';
import { inject, injectable, postConstruct } from '@theia/core/shared/inversify';

import { AqpConfigService } from '../aqp/aqp-config-service';
import { AqpViewIds } from '../../common/aqp-protocol';
import { AqpWidgetBase } from './aqp-widget-base';

/**
 * AQP Management Engine widget — embeds the Vite frontend's
 * `/manage` (Workload Studio), `/cluster-mgmt` (cluster pods), and
 * `/cloudflare` (edge studio) routes in an iframe so Theia users
 * have one-click access to direct workload control without leaving
 * the IDE.
 *
 * The iframe targets the configured AQP frontend origin
 * (`AqpConfigService.load().apiUrl` swapped for the matching
 * frontend origin via `AQP_THEIA_FRONTEND_URL`). Session cookies
 * flow naturally — both surfaces share the same backend trust
 * boundary.
 *
 * Halt fan-out reuses the existing KillSwitch component inside the
 * embedded Vite SPA; Theia operators interact with it like any other
 * browser surface.
 */

interface ManagementWidgetState {
    activeView: 'manage' | 'cluster-mgmt' | 'cloudflare';
    frontendUrl: string;
    loading: boolean;
    error?: string;
}

const FRONTEND_PATHS: Record<ManagementWidgetState['activeView'], string> = {
    manage: '/manage',
    'cluster-mgmt': '/cluster-mgmt',
    cloudflare: '/cloudflare',
};

@injectable()
export class ManagementWidget extends AqpWidgetBase {

    static readonly ID = AqpViewIds.MANAGEMENT;
    static readonly LABEL = 'AQP: Management Engine';

    @inject(AqpConfigService)
    protected readonly aqpConfig!: AqpConfigService;

    private state: ManagementWidgetState = {
        activeView: 'manage',
        frontendUrl: '',
        loading: true,
    };

    @postConstruct()
    protected init(): void {
        this.id = ManagementWidget.ID;
        this.title.label = ManagementWidget.LABEL;
        this.title.caption = ManagementWidget.LABEL;
        this.title.closable = true;
        this.title.iconClass = 'codicon codicon-server';
        this.setupSubscriptions();
        void this.loadFrontendUrl();
    }

    private async loadFrontendUrl(): Promise<void> {
        try {
            const cfg = await this.aqpConfig.load();
            // Per-deployment env: AQP_THEIA_FRONTEND_URL (set in
            // browser.Dockerfile or via runtime config) overrides the
            // API URL when the frontend lives on a different origin
            // behind the same Cloudflare edge.
            const frontendUrl = (cfg.aqp.frontendUrl || cfg.aqp.apiBaseUrl || '').replace(/\/+$/u, '');
            this.state = { ...this.state, frontendUrl, loading: false };
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this.state = { ...this.state, loading: false, error: message };
        }
        this.update();
    }

    protected renderBody(): React.ReactNode {
        const { activeView, frontendUrl, loading, error } = this.state;

        if (loading) {
            return (
                <div className="theia-ReactWidget" style={{ padding: 16 }}>
                    Loading management engine…
                </div>
            );
        }

        if (error || !frontendUrl) {
            return (
                <div className="theia-ReactWidget" style={{ padding: 16 }}>
                    <strong>Management Engine unavailable.</strong>
                    <p style={{ marginTop: 8, fontSize: 12, color: 'var(--theia-descriptionForeground)' }}>
                        {error
                            ? `Failed to load AQP runtime config: ${error}`
                            : 'AQP_THEIA_FRONTEND_URL is not configured; set it on the Theia backend.'}
                    </p>
                </div>
            );
        }

        const src = `${frontendUrl}${FRONTEND_PATHS[activeView]}`;
        return (
            <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                <div style={{
                    display: 'flex',
                    gap: 8,
                    padding: 8,
                    borderBottom: '1px solid var(--theia-panel-border)',
                }}>
                    {(['manage', 'cluster-mgmt', 'cloudflare'] as const).map(view => (
                        <button
                            key={view}
                            type="button"
                            onClick={() => {
                                this.state = { ...this.state, activeView: view };
                                this.update();
                            }}
                            className="theia-button"
                            disabled={view === activeView}
                        >
                            {view === 'manage' ? 'Workloads' : view === 'cluster-mgmt' ? 'Cluster pods' : 'Cloudflare'}
                        </button>
                    ))}
                </div>
                <iframe
                    title={`AQP ${activeView}`}
                    src={src}
                    style={{
                        flex: 1,
                        border: 'none',
                        width: '100%',
                        background: 'var(--theia-editor-background)',
                    }}
                    // The Vite SPA serves same-origin auth cookies; the
                    // iframe inherits them. We deliberately do NOT
                    // pass token material via postMessage; the session
                    // cookie + Cloudflare Access JWT (when present at
                    // the edge) are sufficient.
                    sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads"
                />
            </div>
        );
    }
}
