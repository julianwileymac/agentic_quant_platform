/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import '../../src/browser/style/aqp-theme.css';

import {
    CommandContribution,
    FilterContribution,
    MenuContribution,
} from '@theia/core';
import { FrontendApplicationContribution } from '@theia/core/lib/browser';
import { ContainerModule } from '@theia/core/shared/inversify';

import { AqpAboutDialogContribution } from './about/aqp-about-dialog-contribution';
import { AqpFilterContribution } from './filters/aqp-filter-contribution';
import { AqpWindowTitleContribution } from './window/aqp-window-title-contribution';

/**
 * White-labels the Theia shell as AQP IDE. Purely cosmetic + filtering — no
 * HTTP, no widgets, no commands beyond `aqp.shell.*`.
 *
 * Loaded as a compile-time frontend extension via the `theiaExtensions` entry
 * in this package's package.json.
 */
export default new ContainerModule(bind => {
    bind(AqpFilterContribution).toSelf().inSingletonScope();
    bind(FilterContribution).toService(AqpFilterContribution);

    bind(AqpWindowTitleContribution).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(AqpWindowTitleContribution);

    bind(AqpAboutDialogContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(AqpAboutDialogContribution);
    bind(MenuContribution).toService(AqpAboutDialogContribution);
});
