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
import {
    Auth0Client,
    createAuth0Client,
    GetTokenSilentlyVerboseResponse,
    User as Auth0User,
} from '@auth0/auth0-spa-js';

import { AqpConfigService } from '../aqp/aqp-config-service';

export interface AqpAuthState {
    readonly isAuthenticated: boolean;
    readonly isReady: boolean;
    readonly user?: Auth0User;
    readonly error?: string;
}

const INITIAL_STATE: AqpAuthState = {
    isAuthenticated: false,
    isReady: false,
};

/**
 * Singleton Auth0Client wrapper plus FrontendApplicationContribution hook
 * that (a) bootstraps the SDK from the runtime config served by the Theia
 * backend, (b) completes any `?code=&state=` redirect callback in the URL,
 * and (c) emits an AqpAuthState whenever login / logout / silent refresh
 * succeeds.
 *
 * Widgets consume the client through `<Auth0Bridge>` (see
 * auth0-react-bridge.tsx) which passes the SAME client instance into
 * `<Auth0Provider client=...>` so React hooks (`useAuth0`, `useUser`) see
 * the same login state as the rest of the extension. This sidesteps the
 * "one Provider per React root" trap that Theia's multi-root ReactWidget
 * model otherwise hits (see auth0/auth0-react#324).
 */
@injectable()
export class Auth0Service implements FrontendApplicationContribution {

    @inject(AqpConfigService)
    protected readonly cfg: AqpConfigService;

    @inject(ILogger)
    protected readonly logger: ILogger;

    private client?: Auth0Client;
    private state: AqpAuthState = INITIAL_STATE;
    private readonly _onChange = new Emitter<AqpAuthState>();
    readonly onAuthStateChanged: Event<AqpAuthState> = this._onChange.event;

    /** Resolved once the SDK has finished bootstrap + any redirect callback. */
    private readyResolve?: () => void;
    readonly ready: Promise<void> = new Promise(resolve => { this.readyResolve = resolve; });

    async onStart(_app: FrontendApplication): Promise<void> {
        try {
            const cfg = await this.cfg.load();
            const auth0 = cfg.auth0;
            if (!auth0?.domain || !auth0?.clientId || !auth0?.audience) {
                this.logger.warn(
                    '[aqp-ext] Auth0 config is incomplete (domain, clientId, or audience missing). '
                    + 'The AQP login button will be disabled. Set AQP_THEIA_AUTH0_* env vars on the Theia backend.'
                );
                this.setState({ ...INITIAL_STATE, isReady: true, error: 'auth0 not configured' });
                return;
            }

            this.client = await createAuth0Client({
                domain: auth0.domain,
                clientId: auth0.clientId,
                authorizationParams: {
                    redirect_uri: auth0.redirectUri,
                    audience: auth0.audience,
                    scope: auth0.scope,
                    ...(auth0.organization ? { organization: auth0.organization } : {}),
                },
                // Refresh tokens with rotation avoid the third-party-cookie
                // failure mode (Safari, Brave) that hidden-iframe silent
                // refresh hits.
                useRefreshTokens: true,
                cacheLocation: 'localstorage',
            });

            await this.handleRedirectCallback();
            await this.refreshState();
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this.logger.error('[aqp-ext] Auth0 bootstrap failed:', message);
            this.setState({ ...INITIAL_STATE, isReady: true, error: message });
        } finally {
            this.readyResolve?.();
        }
    }

    /**
     * Detect the `?code=&state=` query that Auth0 appends after a
     * successful authorize redirect, exchange it for tokens, then clean the
     * URL so a page reload doesn't replay the (now-consumed) code.
     */
    protected async handleRedirectCallback(): Promise<void> {
        if (!this.client) {
            return;
        }
        const params = new URLSearchParams(window.location.search);
        const hasCallback = params.has('code') && params.has('state');
        if (!hasCallback) {
            return;
        }
        try {
            await this.client.handleRedirectCallback();
            const cleanUrl = window.location.origin + window.location.pathname;
            window.history.replaceState({}, document.title, cleanUrl);
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this.logger.error('[aqp-ext] Auth0 redirect-callback failed:', message);
        }
    }

    protected async refreshState(): Promise<void> {
        if (!this.client) {
            this.setState({ ...INITIAL_STATE, isReady: true });
            return;
        }
        try {
            const isAuthenticated = await this.client.isAuthenticated();
            const user = isAuthenticated ? await this.client.getUser() : undefined;
            this.setState({ isAuthenticated, isReady: true, user });
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this.logger.error('[aqp-ext] Auth0 isAuthenticated check failed:', message);
            this.setState({ ...INITIAL_STATE, isReady: true, error: message });
        }
    }

    protected setState(next: AqpAuthState): void {
        this.state = next;
        this._onChange.fire(next);
    }

    getState(): AqpAuthState {
        return this.state;
    }

    getClient(): Auth0Client | undefined {
        return this.client;
    }

    async login(): Promise<void> {
        await this.ready;
        if (!this.client) {
            throw new Error('Auth0 is not configured.');
        }
        await this.client.loginWithRedirect();
    }

    async logout(): Promise<void> {
        await this.ready;
        if (!this.client) {
            return;
        }
        await this.client.logout({ logoutParams: { returnTo: window.location.origin } });
        this.setState({ ...INITIAL_STATE, isReady: true });
    }

    /**
     * Returns a valid access token for the AQP API audience, refreshing
     * silently when needed. Returns `undefined` (rather than throwing) when
     * the user is not logged in - callers can surface a Login prompt.
     */
    async getAccessToken(): Promise<string | undefined> {
        await this.ready;
        if (!this.client) {
            return undefined;
        }
        try {
            return await this.client.getTokenSilently();
        } catch (err) {
            // login_required / consent_required / missing_refresh_token are
            // all "user must re-auth" signals. Don't poison logs with them
            // at error level.
            this.logger.debug('[aqp-ext] getTokenSilently failed:', err instanceof Error ? err.message : err);
            return undefined;
        }
    }

    /**
     * Verbose variant used by widgets that want to introspect the audience
     * and scope the SDK ultimately requested (debugging Auth0 dashboard
     * misconfigurations).
     */
    async getAccessTokenVerbose(): Promise<GetTokenSilentlyVerboseResponse | undefined> {
        await this.ready;
        if (!this.client) {
            return undefined;
        }
        try {
            return await this.client.getTokenSilently({ detailedResponse: true });
        } catch {
            return undefined;
        }
    }
}
