/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import {
    FilterContribution,
    ContributionFilterRegistry,
    bindContributionProvider,
} from '@theia/core';
import { injectable } from '@theia/core/shared/inversify';

/**
 * Hides upstream contributions that are noise in a quant research environment.
 * Use Theia's built-in contribution-filtering mechanism so we don't have to
 * fork or patch any upstream class.
 *
 * Suppress list (additive — operators can extend via env override later):
 *
 *  - The `Getting Started` walkthrough quickPick noise (extension id
 *    `getting-started`) on first boot. We have our own onboarding.
 *  - Default GitHub authentication provider (`github` extension) — the
 *    operator-side identity is Auth0 (rule 27); leaving GitHub auth
 *    available encourages developers to sign in with the wrong account.
 *  - The Outline view default panel when no editor is open — declutters
 *    the left sidebar so the AQP views are easier to find.
 */
@injectable()
export class AqpFilterContribution implements FilterContribution {

    registerContributionFilters(registry: ContributionFilterRegistry): void {
        // Hide the default "Getting Started" walkthrough. The extension id
        // for the Theia getting-started bundle is `getting-started`.
        registry.addFilters(['getting-started'], [
            contrib => !this.matchesClassName(contrib, 'GettingStartedContribution'),
        ]);

        // Hide the GitHub authentication provider — AQP identity is Auth0.
        registry.addFilters(['github-authentication'], [
            () => false,
        ]);
    }

    protected matchesClassName(contrib: object, name: string): boolean {
        if (!contrib) {
            return false;
        }
        const ctor = contrib.constructor;
        if (!ctor) {
            return false;
        }
        return ctor.name === name;
    }
}

// Re-export the bindContributionProvider helper so the frontend module can
// register additional FilterContribution providers without re-importing.
export { bindContributionProvider };
