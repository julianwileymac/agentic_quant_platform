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

import { AqpMcpRegistrar } from '../mcp/aqp-mcp-registrar';
import { AqpMcpCommandIds } from '../../common/aqp-mcp-protocol';
import { describeSurfaceConfig } from '../mcp/aqp-mcp-server-spec';

const AQP_CATEGORY = 'AQP';

const RECONNECT_ALL: Command = {
    id: AqpMcpCommandIds.RECONNECT_ALL,
    category: AQP_CATEGORY,
    label: 'MCP — Reconnect All',
};

const SHOW_STATUS: Command = {
    id: AqpMcpCommandIds.SHOW_STATUS,
    category: AQP_CATEGORY,
    label: 'MCP — Show Status',
};

/**
 * Exposes the two operator-facing MCP commands to the command palette and
 * the Help menu. Both commands are read/write idempotent and safe to bind
 * to a keyboard shortcut later if the operator wants one.
 */
@injectable()
export class AqpMcpContribution implements CommandContribution, MenuContribution {

    @inject(AqpMcpRegistrar)
    protected readonly registrar!: AqpMcpRegistrar;

    @inject(MessageService)
    protected readonly messages!: MessageService;

    registerCommands(registry: CommandRegistry): void {
        registry.registerCommand(RECONNECT_ALL, {
            execute: async () => {
                try {
                    await this.registrar.reconnect();
                    this.messages.info('AQP: MCP servers re-registered.');
                } catch (err) {
                    const message = err instanceof Error ? err.message : String(err);
                    this.messages.error(`AQP: MCP reconnect failed: ${message}`);
                }
            },
        });
        registry.registerCommand(SHOW_STATUS, {
            execute: () => {
                const status = this.registrar.getStatus();
                if (status.size === 0) {
                    this.messages.warn('AQP: no MCP surfaces registered yet.');
                    return;
                }
                const lines: string[] = ['AQP MCP servers:'];
                for (const [name, s] of status) {
                    const url = describeSurfaceConfig({ url: s.url, audience: s.audience });
                    const stamp = s.lastRegisteredAt
                        ? new Date(s.lastRegisteredAt).toISOString()
                        : '(never)';
                    const state = s.ok ? 'OK' : `ERROR: ${s.error ?? 'unknown'}`;
                    lines.push(`  ${name} -> ${url}  [${state}]  last: ${stamp}`);
                }
                this.messages.info(lines.join('\n'));
            },
        });
    }

    registerMenus(menus: MenuModelRegistry): void {
        // Add to the Help menu so operators can find both commands without
        // a keybinding. The `0_aqp_mcp` order keeps them grouped together
        // below the AQP About entry from aqp-shell.
        menus.registerMenuAction(CommonMenus.HELP, {
            commandId: RECONNECT_ALL.id,
            label: 'AQP MCP — Reconnect All',
            order: '0_aqp_mcp_1',
        });
        menus.registerMenuAction(CommonMenus.HELP, {
            commandId: SHOW_STATUS.id,
            label: 'AQP MCP — Show Status',
            order: '0_aqp_mcp_2',
        });
    }
}
