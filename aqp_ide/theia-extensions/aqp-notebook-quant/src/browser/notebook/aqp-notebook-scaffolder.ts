/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { ILogger, MessageService } from '@theia/core';
import URI from '@theia/core/lib/common/uri';
import { OpenerService, open } from '@theia/core/lib/browser';
import { FileService } from '@theia/filesystem/lib/browser/file-service';
import { WorkspaceService } from '@theia/workspace/lib/browser/workspace-service';
import { inject, injectable } from '@theia/core/shared/inversify';

import { AQP_NOTEBOOK_HELPER_CELL } from '../../common/aqp-notebook-protocol';

/**
 * Scaffolds a `.ipynb` with the AQP helper imports cell pre-populated and
 * opens it in the editor. The notebook JSON is the standard Jupyter
 * shape (nbformat v4) so any kernel that handles `.ipynb` can run the
 * cell — there is no AQP-specific kernel requirement.
 */
@injectable()
export class AqpNotebookScaffolder {

    @inject(WorkspaceService)
    protected readonly workspace!: WorkspaceService;

    @inject(FileService)
    protected readonly files!: FileService;

    @inject(OpenerService)
    protected readonly opener!: OpenerService;

    @inject(MessageService)
    protected readonly messages!: MessageService;

    @inject(ILogger)
    protected readonly logger!: ILogger;

    async createAndOpen(): Promise<void> {
        const root = await this.resolveRoot();
        if (!root) {
            this.messages.warn('AQP: cannot scaffold notebook — no workspace open.');
            return;
        }
        const filename = this.proposeFilename();
        const fileUri = root.resolve(filename);
        const json = this.buildNotebookJson();
        try {
            await this.files.create(fileUri, json, { overwrite: false });
        } catch (err) {
            this.logger.warn('[aqp-notebook-quant] Notebook create failed; retrying with a unique name:', err);
            const altUri = root.resolve(this.proposeFilename(true));
            await this.files.create(altUri, json);
            await open(this.opener, altUri);
            this.messages.info(`AQP: scaffolded ${altUri.path.base}.`);
            return;
        }
        await open(this.opener, fileUri);
        this.messages.info(`AQP: scaffolded ${filename}.`);
    }

    protected async resolveRoot(): Promise<URI | undefined> {
        await this.workspace.ready;
        const roots = this.workspace.tryGetRoots();
        if (roots.length === 0) {
            return undefined;
        }
        return roots[0].resource;
    }

    protected proposeFilename(forceUnique = false): string {
        const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        return forceUnique
            ? `aqp-notebook-${stamp}-${Math.random().toString(36).slice(2, 6)}.ipynb`
            : `aqp-notebook-${stamp}.ipynb`;
    }

    protected buildNotebookJson(): string {
        const ipynb = {
            cells: [
                {
                    cell_type: 'code',
                    metadata: {},
                    source: AQP_NOTEBOOK_HELPER_CELL.split('\n').map((line, idx, arr) =>
                        idx === arr.length - 1 ? line : line + '\n',
                    ),
                    execution_count: null as number | null,
                    outputs: [] as unknown[],
                },
            ],
            metadata: {
                kernelspec: {
                    display_name: 'Python 3',
                    language: 'python',
                    name: 'python3',
                },
                language_info: {
                    name: 'python',
                    version: '3.11',
                },
                aqp: {
                    scaffolder: 'theia-ide-aqp-notebook-quant-ext',
                    helper_cell_version: '1',
                },
            },
            nbformat: 4,
            nbformat_minor: 5,
        };
        return JSON.stringify(ipynb, undefined, 2);
    }
}
