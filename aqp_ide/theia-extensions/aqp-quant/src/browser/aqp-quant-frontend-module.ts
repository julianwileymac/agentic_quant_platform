/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { CommandContribution, MenuContribution } from '@theia/core';
import {
    FrontendApplicationContribution,
    WidgetFactory,
} from '@theia/core/lib/browser';
import { ContainerModule } from '@theia/core/shared/inversify';

import {
    BacktestRunnerViewContribution,
    RunInspectorViewContribution,
    SpecAuthorViewContribution,
} from './commands/aqp-quant-view-contributions';
import { AqpRuntimeClient } from './services/aqp-runtime-client';
import { AqpWsClient } from './services/aqp-ws-client';
import { BacktestRunnerWidget } from './widgets/backtest-runner-widget';
import { RunInspectorWidget } from './widgets/run-inspector-widget';
import { SpecAuthorWidget } from './widgets/spec-author-widget';

export default new ContainerModule(bind => {
    // --- Services ----------------------------------------------------------
    bind(AqpRuntimeClient).toSelf().inSingletonScope();
    bind(AqpWsClient).toSelf().inSingletonScope();

    // --- Widgets + factories ----------------------------------------------
    bind(SpecAuthorWidget).toSelf();
    bind(WidgetFactory).toDynamicValue(ctx => ({
        id: SpecAuthorWidget.ID,
        createWidget: () => ctx.container.get(SpecAuthorWidget),
    })).inSingletonScope();

    bind(RunInspectorWidget).toSelf();
    bind(WidgetFactory).toDynamicValue(ctx => ({
        id: RunInspectorWidget.ID,
        createWidget: () => ctx.container.get(RunInspectorWidget),
    })).inSingletonScope();

    bind(BacktestRunnerWidget).toSelf();
    bind(WidgetFactory).toDynamicValue(ctx => ({
        id: BacktestRunnerWidget.ID,
        createWidget: () => ctx.container.get(BacktestRunnerWidget),
    })).inSingletonScope();

    // --- View contributions ------------------------------------------------
    bind(SpecAuthorViewContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(SpecAuthorViewContribution);
    bind(MenuContribution).toService(SpecAuthorViewContribution);
    bind(FrontendApplicationContribution).toService(SpecAuthorViewContribution);

    bind(RunInspectorViewContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(RunInspectorViewContribution);
    bind(MenuContribution).toService(RunInspectorViewContribution);
    bind(FrontendApplicationContribution).toService(RunInspectorViewContribution);

    bind(BacktestRunnerViewContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(BacktestRunnerViewContribution);
    bind(MenuContribution).toService(BacktestRunnerViewContribution);
    bind(FrontendApplicationContribution).toService(BacktestRunnerViewContribution);
});
