/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { ILogger } from '@theia/core';
import {
    FrontendApplication,
    FrontendApplicationContribution,
} from '@theia/core/lib/browser';
import { inject, injectable } from '@theia/core/shared/inversify';

import { AqpTenancyStore, AqpTenancy } from 'theia-ide-aqp-ext/lib/browser/aqp/aqp-tenancy-store';

const TITLE_PREFIX = 'AQP IDE';

/**
 * Sets `document.title` to `AQP IDE — <tenancy>` whenever the active AQP
 * tenancy changes. Falls back to plain `AQP IDE` when no tenancy is set.
 *
 * Why not rebind WindowTitleService directly: Theia's WindowTitleService
 * concatenates many parts (editor name, workspace, dirty marker, ...) into
 * the final title and is heavily customised by core packages. Driving
 * document.title from the outside keeps this extension additive and avoids
 * recreating the entire title-assembly pipeline.
 */
@injectable()
export class AqpWindowTitleContribution implements FrontendApplicationContribution {

    @inject(AqpTenancyStore)
    protected readonly tenancy!: AqpTenancyStore;

    @inject(ILogger)
    protected readonly logger!: ILogger;

    async onStart(_app: FrontendApplication): Promise<void> {
        try {
            this.apply(this.tenancy.get());
            this.tenancy.onTenancyChanged(next => this.apply(next));
        } catch (err) {
            this.logger.warn('[aqp-shell] Window title contribution failed to bind:', err);
        }
    }

    protected apply(state: AqpTenancy): void {
        const parts: string[] = [];
        if (state.org) {
            parts.push(state.org);
        }
        if (state.workspace) {
            parts.push(state.workspace);
        }
        if (state.lab) {
            parts.push(state.lab);
        }
        const suffix = parts.length > 0 ? ` — ${parts.join(' / ')}` : '';
        if (typeof document !== 'undefined') {
            document.title = `${TITLE_PREFIX}${suffix}`;
        }
    }
}
