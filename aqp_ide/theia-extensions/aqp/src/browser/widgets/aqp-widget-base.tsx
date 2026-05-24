/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import * as React from '@theia/core/shared/react';
import { CommandService, MessageService } from '@theia/core';
import { ReactWidget } from '@theia/core/lib/browser';
import { inject, injectable } from '@theia/core/shared/inversify';

import { Auth0Service, AqpAuthState } from '../auth/auth0-service';
import { Auth0Bridge } from '../auth/auth0-react-bridge';
import { AqpApiService } from '../aqp/aqp-api-service';
import { AqpTenancyStore, AqpTenancy } from '../aqp/aqp-tenancy-store';
import { AqpCommandIds } from '../../common/aqp-protocol';

/**
 * Shared base for every AQP widget. Subclasses implement `renderBody()`
 * (which runs INSIDE the Auth0Bridge React tree and AFTER the
 * "is logged in" gate has fired) plus optionally `getHeaderActions()` for
 * a per-widget toolbar.
 *
 * The base wires:
 *  - Auth0Service state changes -> this.update()
 *  - Tenancy changes -> this.update()
 *  - "Not logged in" -> a centred Login button instead of the body
 *  - "Auth0 not configured" -> a short config error with a link to README
 *  - Auth0Bridge wrapping so children can call useAuth0() / useUser()
 */
@injectable()
export abstract class AqpWidgetBase extends ReactWidget {

    @inject(Auth0Service)
    protected readonly auth!: Auth0Service;

    @inject(AqpApiService)
    protected readonly api!: AqpApiService;

    @inject(AqpTenancyStore)
    protected readonly tenancy!: AqpTenancyStore;

    @inject(MessageService)
    protected readonly messages!: MessageService;

    @inject(CommandService)
    protected readonly commands!: CommandService;

    protected authState: AqpAuthState = { isAuthenticated: false, isReady: false };
    protected tenancyState: AqpTenancy = {};

    protected setupSubscriptions(): void {
        this.authState = this.auth.getState();
        this.tenancyState = this.tenancy.get();
        this.toDispose.push(this.auth.onAuthStateChanged(state => {
            this.authState = state;
            this.update();
        }));
        this.toDispose.push(this.tenancy.onTenancyChanged(state => {
            this.tenancyState = state;
            this.update();
        }));
    }

    protected render(): React.ReactNode {
        return (
            <Auth0Bridge auth0Service={this.auth}>
                <div className="aqp-widget">
                    {this.renderHeader()}
                    {this.renderContent()}
                </div>
            </Auth0Bridge>
        );
    }

    protected renderHeader(): React.ReactNode {
        const actions = this.getHeaderActions?.() ?? [];
        return (
            <div className="aqp-widget-header">
                <div className="aqp-widget-title">{this.title.label}</div>
                <div className="aqp-widget-actions">
                    {actions.map((a, i) => (
                        <button
                            key={`${a.label}-${i}`}
                            className="theia-button secondary"
                            onClick={() => a.onClick()}
                            disabled={a.disabled}
                            title={a.tooltip}
                        >
                            {a.label}
                        </button>
                    ))}
                </div>
            </div>
        );
    }

    protected renderContent(): React.ReactNode {
        if (!this.authState.isReady) {
            return <div className="aqp-widget-message">Loading AQP configuration...</div>;
        }
        if (this.authState.error === 'auth0 not configured') {
            return (
                <div className="aqp-widget-message">
                    <p>Auth0 is not configured for this Theia instance.</p>
                    <p>
                        Set <code>AQP_THEIA_AUTH0_DOMAIN</code>,{' '}
                        <code>AQP_THEIA_AUTH0_CLIENT_ID</code>, and{' '}
                        <code>AQP_THEIA_AUTH0_AUDIENCE</code> on the Theia backend, then reload.
                    </p>
                </div>
            );
        }
        if (!this.authState.isAuthenticated) {
            return (
                <div className="aqp-widget-message">
                    <p>You are not signed in to AQP.</p>
                    <button
                        className="theia-button"
                        onClick={() => this.commands.executeCommand(AqpCommandIds.LOGIN)}
                    >
                        Sign in
                    </button>
                </div>
            );
        }
        return this.renderBody();
    }

    protected abstract renderBody(): React.ReactNode;

    /** Override to add per-widget toolbar buttons rendered in the header. */
    protected getHeaderActions?(): Array<{
        label: string;
        onClick: () => void;
        disabled?: boolean;
        tooltip?: string;
    }>;
}
