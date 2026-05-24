/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { Application, Request, Response } from '@theia/core/shared/express';
import { BackendApplicationContribution } from '@theia/core/lib/node/backend-application';
import { injectable } from '@theia/core/shared/inversify';

import { AqpRuntimeConfig } from '../common/aqp-protocol';

/**
 * Serves the runtime AQP + Auth0 config to the browser bundle on GET /aqp/config.
 *
 * Why runtime, not bake-time:
 * Theia's webpack does NOT inline arbitrary process.env values into the
 * browser bundle. Baking Auth0 client ids into the JS at build time also
 * means a separate image per environment. Instead we read env on the Node
 * backend and serve the config as JSON. The same container image then runs
 * for dev / staging / prod by varying env vars only.
 *
 * No secrets pass through this endpoint: an Auth0 SPA client_id is a public
 * value (the PKCE flow makes it safe to expose), the audience is the AQP
 * API identifier, and the AQP base URL is similarly non-sensitive.
 */
@injectable()
export class AqpConfigEndpoint implements BackendApplicationContribution {

    protected static PATH = '/aqp/config';

    configure(app: Application): void {
        app.get(AqpConfigEndpoint.PATH, (_req: Request, res: Response) => {
            // Use `||` (not `??`) so that an env var set to "" (which is
            // what `ENV KEY=""` in the Dockerfile produces - present but
            // empty) falls back to the default. `??` only treats null and
            // undefined as missing.
            const publicOrigin = process.env.AQP_THEIA_PUBLIC_ORIGIN || '';
            const defaultRedirect = publicOrigin ? `${publicOrigin}/` : '';

            const apiBaseUrl = process.env.AQP_THEIA_API_URL || 'http://localhost:8000';
            const frontendUrl = process.env.AQP_THEIA_FRONTEND_URL || apiBaseUrl;
            const providersUrl = process.env.AQP_THEIA_PROVIDERS_URL
                || `${apiBaseUrl.replace(/\/+$/u, '')}/auth/providers`;

            const config: AqpRuntimeConfig = {
                auth0: {
                    domain: process.env.AQP_THEIA_AUTH0_DOMAIN || '',
                    clientId: process.env.AQP_THEIA_AUTH0_CLIENT_ID || '',
                    audience: process.env.AQP_THEIA_AUTH0_AUDIENCE || '',
                    scope: process.env.AQP_THEIA_AUTH0_SCOPE || 'openid profile email offline_access',
                    redirectUri: process.env.AQP_THEIA_AUTH0_REDIRECT_URI || defaultRedirect,
                    organization: process.env.AQP_THEIA_AUTH0_ORGANIZATION || undefined,
                },
                aqp: {
                    apiBaseUrl,
                    frontendUrl,
                    providersUrl,
                },
            };

            // Disable any caching - operators rotate env vars without
            // bumping a build hash, and the config must reflect that on
            // the next page load.
            res.set('Cache-Control', 'no-store');
            res.json(config);
        });
    }
}
