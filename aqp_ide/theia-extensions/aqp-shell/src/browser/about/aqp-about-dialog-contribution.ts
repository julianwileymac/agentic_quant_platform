/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import {
    Command,
    CommandContribution,
    CommandRegistry,
    MenuContribution,
    MenuModelRegistry,
    MessageService,
} from '@theia/core';
import { CommonMenus } from '@theia/core/lib/browser';
import { inject, injectable } from '@theia/core/shared/inversify';

import { AqpConfigService } from 'theia-ide-aqp-ext/lib/browser/aqp/aqp-config-service';

const ABOUT_AQP_IDE: Command = {
    id: 'aqp.shell.about',
    category: 'AQP',
    label: 'About AQP IDE',
};

/**
 * Adds an `AQP → About AQP IDE` menu entry that opens a MessageService
 * notification with the AQP IDE branding block (version, API base URL,
 * frontend URL, tenancy summary).
 *
 * Kept as a notification (rather than a modal dialog) so this extension stays
 * lean — the upstream Theia `AboutDialog` is not replaced; we simply add an
 * AQP-flavoured peer.
 */
@injectable()
export class AqpAboutDialogContribution implements CommandContribution, MenuContribution {

    @inject(AqpConfigService)
    protected readonly cfg!: AqpConfigService;

    @inject(MessageService)
    protected readonly messages!: MessageService;

    registerCommands(registry: CommandRegistry): void {
        registry.registerCommand(ABOUT_AQP_IDE, {
            execute: async () => {
                const cfg = await this.cfg.load();
                const lines = [
                    'AQP IDE — Theia 1.72 + AQP extensions',
                    `API: ${cfg.aqp.apiBaseUrl || '(unset)'}`,
                    `Frontend: ${cfg.aqp.frontendUrl || '(falls back to API)'}`,
                    `Auth0 domain: ${cfg.auth0.domain || '(unset)'}`,
                    `Auth0 audience: ${cfg.auth0.audience || '(unset)'}`,
                ];
                this.messages.info(lines.join('\n'));
            },
        });
    }

    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(CommonMenus.HELP, {
            commandId: ABOUT_AQP_IDE.id,
            label: ABOUT_AQP_IDE.label,
            order: '0_aqp',
        });
    }
}
