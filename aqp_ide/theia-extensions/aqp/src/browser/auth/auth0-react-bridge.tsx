/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import * as React from '@theia/core/shared/react';
import { Auth0Provider } from '@auth0/auth0-react';
import { Auth0Client } from '@auth0/auth0-spa-js';

import { Auth0Service } from './auth0-service';

/**
 * Wraps a widget's React tree in an Auth0Provider that points at the SAME
 * `Auth0Client` instance owned by Auth0Service. This is the pattern
 * sanctioned by auth0/auth0-react v2.5+ via the new `client` prop
 * (auth0/auth0-react#1041, merged March 2026): instead of letting the
 * Provider construct its own client (which would create a SECOND login
 * session for each ReactWidget root), pass in the shared singleton.
 *
 * Without this bridge, every ReactWidget would either need to re-login
 * (one Auth0Client per widget) or fail with the "you forgot to wrap your
 * component in <Auth0Provider>" error documented in auth0/auth0-react#324.
 */
export interface Auth0BridgeProps {
    readonly auth0Service: Auth0Service;
    readonly children: React.ReactNode;
}

export const Auth0Bridge: React.FC<Auth0BridgeProps> = ({ auth0Service, children }) => {
    const client = auth0Service.getClient();
    if (!client) {
        // Auth0 is not configured; render children without the Provider.
        // Widgets that depend on useAuth0() will receive the not-authenticated
        // default and should fall back to a "Login" call to action.
        return <>{children}</>;
    }
    return (
        <Auth0Provider client={client as Auth0Client} onRedirectCallback={() => {/* handled by Auth0Service */}}>
            {children}
        </Auth0Provider>
    );
};
