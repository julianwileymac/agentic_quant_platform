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
import {
    CommonMenus,
    ConfirmDialog,
    Dialog,
    KeybindingContribution,
    KeybindingRegistry,
} from '@theia/core/lib/browser';
import { inject, injectable } from '@theia/core/shared/inversify';

import { AqpApiService } from '../aqp/aqp-api-service';
import { AqpCommandIds, KILL_SWITCH_ENDPOINTS } from '../../common/aqp-protocol';
import { AQP_CATEGORY } from './aqp-view-contributions';

const HALT_ALL: Command = {
    id: AqpCommandIds.HALT_ALL,
    category: AQP_CATEGORY,
    label: 'Halt EVERYTHING (kill-switch)',
};

/**
 * Global kill-switch command. Mirrors the AQP Vite frontend's
 * `KillSwitch` component:
 *
 *   POST /agents/halt, /paper/stop-all, /bots/halt-all, /rl/halt-all,
 *        /quant-agents/halt, /workflows/halt, /terraform/halt,
 *        /assistants/halt  (in parallel)
 *
 * Always shown behind a friction dialog because clicking it WILL stop
 * paper-trading sessions and revoke active terraform runs.
 *
 * Bound to ctrlcmd+alt+h for operator-grade muscle memory.
 */
@injectable()
export class AqpHaltContribution implements CommandContribution, MenuContribution, KeybindingContribution {

    @inject(AqpApiService)
    protected readonly api: AqpApiService;

    @inject(MessageService)
    protected readonly messages: MessageService;

    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(HALT_ALL, {
            execute: () => this.haltAll(),
        });
    }

    registerMenus(menus: MenuModelRegistry): void {
        // Helps make this discoverable from the menu bar in addition to the
        // command palette / status bar / keybinding.
        menus.registerMenuAction(CommonMenus.HELP, {
            commandId: HALT_ALL.id,
            label: HALT_ALL.label,
            order: 'z_aqp_halt',
        });
    }

    registerKeybindings(keybindings: KeybindingRegistry): void {
        keybindings.registerKeybinding({
            command: HALT_ALL.id,
            keybinding: 'ctrlcmd+alt+h',
            when: '!editorFocus',
        });
    }

    protected async haltAll(): Promise<void> {
        const message = document.createElement('div');
        message.style.whiteSpace = 'pre-line';
        message.textContent =
            'This will halt EVERY long-running AQP runtime on the connected backend:\n\n' +
            '  - agent runs\n' +
            '  - paper-trading sessions\n' +
            '  - bot deployments\n' +
            '  - RL training jobs\n' +
            '  - quant agent crews\n' +
            '  - workflow runs\n' +
            '  - terraform runs\n' +
            '  - assistant sessions\n\n' +
            'Operations in progress will be cancelled. Continue?';

        const confirmed = await new ConfirmDialog({
            title: 'AQP: kill-switch',
            msg: message,
            ok: 'Halt everything',
            cancel: Dialog.CANCEL,
        }).open();
        if (!confirmed) {
            return;
        }

        const outcomes = await Promise.all(
            KILL_SWITCH_ENDPOINTS.map(async path => ({ path, result: await this.api.safePost(path) })),
        );

        const failures = outcomes.filter(o => !o.result.ok);
        if (failures.length === 0) {
            this.messages.info(`AQP: halt-everything fan-out succeeded across ${outcomes.length} endpoints.`);
            return;
        }
        const summary = failures
            .map(o => `${o.path}: HTTP ${o.result.status || 'error'} - ${truncate(o.result.body, 120)}`)
            .join('\n');
        this.messages.error(
            `AQP: halt-everything completed with ${failures.length}/${outcomes.length} failures:\n${summary}`,
        );
    }
}

function truncate(text: string, max: number): string {
    if (!text) {
        return '(no body)';
    }
    return text.length > max ? `${text.slice(0, max)}...` : text;
}
