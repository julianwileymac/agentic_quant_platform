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

import { AqpNotebookCommandIds } from '../../common/aqp-notebook-protocol';
import { AqpNotebookScaffolder } from '../notebook/aqp-notebook-scaffolder';

const AQP_CATEGORY = 'AQP';

const NEW_AQP_NOTEBOOK: Command = {
    id: AqpNotebookCommandIds.NEW_AQP_NOTEBOOK,
    category: AQP_CATEGORY,
    label: 'New AQP Notebook',
};

const SHOW_NOTEBOOK_DOCS: Command = {
    id: AqpNotebookCommandIds.SHOW_NOTEBOOK_DOCS,
    category: AQP_CATEGORY,
    label: 'Open Notebook Docs',
};

/**
 * Exposes the AQP notebook commands to the File menu, Help menu, and
 * command palette.
 */
@injectable()
export class AqpNotebookContribution implements CommandContribution, MenuContribution {

    @inject(AqpNotebookScaffolder)
    protected readonly scaffolder!: AqpNotebookScaffolder;

    @inject(MessageService)
    protected readonly messages!: MessageService;

    registerCommands(registry: CommandRegistry): void {
        registry.registerCommand(NEW_AQP_NOTEBOOK, {
            execute: () => this.scaffolder.createAndOpen(),
        });
        registry.registerCommand(SHOW_NOTEBOOK_DOCS, {
            execute: () => {
                this.messages.info(
                    'AQP: notebook docs live in aqp_ide/docs/notebook.md. ' +
                    'Open it from File → Open File.'
                );
            },
        });
    }

    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(CommonMenus.FILE_NEW, {
            commandId: NEW_AQP_NOTEBOOK.id,
            label: NEW_AQP_NOTEBOOK.label,
            order: '0_aqp_notebook',
        });
        menus.registerMenuAction(CommonMenus.HELP, {
            commandId: SHOW_NOTEBOOK_DOCS.id,
            label: 'AQP Notebook Docs',
            order: '0_aqp_notebook_docs',
        });
    }
}
