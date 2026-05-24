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
import { QuickInputService, QuickPickItem } from '@theia/core/lib/browser/quick-input';
import { inject, injectable } from '@theia/core/shared/inversify';

import { AqpApiService, AqpHttpError } from '../aqp/aqp-api-service';
import { AqpTenancyStore } from '../aqp/aqp-tenancy-store';
import { AqpCommandIds } from '../../common/aqp-protocol';
import { AqpEntityRef } from '../aqp/aqp-types';
import { AQP_CATEGORY, AqpMenus } from './aqp-view-contributions';

const SET_TENANCY: Command = {
    id: AqpCommandIds.SET_TENANCY,
    category: AQP_CATEGORY,
    label: 'Set tenancy (org / team / workspace / project / lab)',
};

interface TenancyEntityPicker {
    readonly title: string;
    readonly path: string;
    apply(value: string | undefined): Promise<void>;
    current(): string | undefined;
}

@injectable()
export class AqpTenancyContribution implements CommandContribution, MenuContribution {

    @inject(AqpApiService)
    protected readonly api: AqpApiService;

    @inject(AqpTenancyStore)
    protected readonly tenancy: AqpTenancyStore;

    @inject(QuickInputService)
    protected readonly quickInput: QuickInputService;

    @inject(MessageService)
    protected readonly messages: MessageService;

    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(SET_TENANCY, {
            execute: () => this.setTenancy(),
        });
    }

    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(AqpMenus.AQP_VIEWS, {
            commandId: SET_TENANCY.id,
            label: SET_TENANCY.label,
            order: '7',
        });
    }

    protected async setTenancy(): Promise<void> {
        const pickers: TenancyEntityPicker[] = [
            {
                title: 'Organisation',
                path: '/orgs',
                apply: async value => this.tenancy.set({ ...this.tenancy.get(), org: value }),
                current: () => this.tenancy.get().org,
            },
            {
                title: 'Team',
                path: '/teams',
                apply: async value => this.tenancy.set({ ...this.tenancy.get(), team: value }),
                current: () => this.tenancy.get().team,
            },
            {
                title: 'Workspace',
                path: '/workspaces',
                apply: async value => this.tenancy.set({ ...this.tenancy.get(), workspace: value }),
                current: () => this.tenancy.get().workspace,
            },
            {
                title: 'Project',
                path: '/projects',
                apply: async value => this.tenancy.set({ ...this.tenancy.get(), project: value }),
                current: () => this.tenancy.get().project,
            },
            {
                title: 'Lab',
                path: '/labs',
                apply: async value => this.tenancy.set({ ...this.tenancy.get(), lab: value }),
                current: () => this.tenancy.get().lab,
            },
        ];

        const which = await this.quickInput.showQuickPick(
            pickers.map(p => ({
                label: p.title,
                description: p.current() ? `currently: ${p.current()}` : '(not set)',
            })),
            { placeholder: 'Pick which tenancy axis to change' },
        );
        if (!which) {
            return;
        }
        const picker = pickers.find(p => p.title === which.label);
        if (!picker) {
            return;
        }

        let entries: AqpEntityRef[];
        try {
            const data = await this.api.get<AqpEntityRef[] | { items?: AqpEntityRef[] }>(picker.path);
            entries = Array.isArray(data) ? data : (data?.items ?? []);
        } catch (err) {
            const message = err instanceof AqpHttpError
                ? `HTTP ${err.status} ${err.statusText}`
                : err instanceof Error ? err.message : String(err);
            this.messages.error(`AQP: could not list ${picker.title}: ${message}`);
            return;
        }
        if (entries.length === 0) {
            this.messages.warn(`AQP: no ${picker.title.toLowerCase()} entries available on the backend.`);
            return;
        }
        const items: QuickPickItem[] = [
            { label: '(unset)', description: 'Clear this tenancy axis' },
            ...entries.map(e => ({
                label: e.name ?? e.slug ?? String(e.id),
                description: e.description,
                detail: `id: ${e.id}`,
            })),
        ];
        const choice = await this.quickInput.showQuickPick(items, {
            placeholder: `Pick a ${picker.title.toLowerCase()}`,
        });
        if (!choice) {
            return;
        }
        if (choice.label === '(unset)') {
            await picker.apply(undefined);
            this.messages.info(`AQP: cleared ${picker.title}.`);
            return;
        }
        const detail = choice.detail ?? '';
        const id = detail.startsWith('id: ') ? detail.slice(4) : choice.label;
        await picker.apply(id);
        this.messages.info(`AQP: set ${picker.title} = ${choice.label} (${id}).`);
    }
}
