/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { CommandContribution, MenuContribution } from '@theia/core';
import { FrontendApplicationContribution } from '@theia/core/lib/browser';
import { ContainerModule } from '@theia/core/shared/inversify';

import { AqpNotebookContribution } from './commands/aqp-notebook-contribution';
import { AqpNotebookScaffolder } from './notebook/aqp-notebook-scaffolder';
import { PerspectiveArrowRenderer } from './notebook/perspective-mime-renderer';

/**
 * Wires the notebook MIME renderer + the scaffolder command into the
 * Theia frontend container.
 */
export default new ContainerModule(bind => {
    bind(PerspectiveArrowRenderer).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(PerspectiveArrowRenderer);

    bind(AqpNotebookScaffolder).toSelf().inSingletonScope();

    bind(AqpNotebookContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(AqpNotebookContribution);
    bind(MenuContribution).toService(AqpNotebookContribution);
});
