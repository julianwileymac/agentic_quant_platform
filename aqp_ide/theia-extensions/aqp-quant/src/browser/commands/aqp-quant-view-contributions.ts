/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import {
    AbstractViewContribution,
    CommonMenus,
} from '@theia/core/lib/browser';
import { Command, CommandRegistry, MenuModelRegistry, MenuPath } from '@theia/core';
import { injectable } from '@theia/core/shared/inversify';

import { AqpQuantCommandIds } from '../../common/aqp-quant-protocol';
import { BacktestRunnerWidget } from '../widgets/backtest-runner-widget';
import { RunInspectorWidget } from '../widgets/run-inspector-widget';
import { SpecAuthorWidget } from '../widgets/spec-author-widget';

const AQP_CATEGORY = 'AQP';

const AQP_QUANT_VIEWS: MenuPath = [...CommonMenus.VIEW_VIEWS, 'aqp-quant'];

const OPEN_SPEC_AUTHOR: Command = {
    id: AqpQuantCommandIds.OPEN_SPEC_AUTHOR,
    category: AQP_CATEGORY,
    label: 'Show Spec Author',
};

const OPEN_RUN_INSPECTOR: Command = {
    id: AqpQuantCommandIds.OPEN_RUN_INSPECTOR,
    category: AQP_CATEGORY,
    label: 'Show Run Inspector',
};

const OPEN_BACKTEST_RUNNER: Command = {
    id: AqpQuantCommandIds.OPEN_BACKTEST_RUNNER,
    category: AQP_CATEGORY,
    label: 'Show Backtest Runner',
};

const ATTACH_RUN: Command = {
    id: AqpQuantCommandIds.ATTACH_RUN,
    category: AQP_CATEGORY,
    label: 'Attach Run Inspector to task id',
};

@injectable()
export class SpecAuthorViewContribution extends AbstractViewContribution<SpecAuthorWidget> {
    constructor() {
        super({
            widgetId: SpecAuthorWidget.ID,
            widgetName: SpecAuthorWidget.LABEL,
            defaultWidgetOptions: { area: 'left', rank: 200 },
            toggleCommandId: OPEN_SPEC_AUTHOR.id,
        });
    }
    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(OPEN_SPEC_AUTHOR, {
            execute: () => this.openView({ activate: true, reveal: true }),
        });
    }
    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(AQP_QUANT_VIEWS, {
            commandId: OPEN_SPEC_AUTHOR.id,
            label: SpecAuthorWidget.LABEL,
            order: '1',
        });
    }
}

@injectable()
export class RunInspectorViewContribution extends AbstractViewContribution<RunInspectorWidget> {

    constructor() {
        super({
            widgetId: RunInspectorWidget.ID,
            widgetName: RunInspectorWidget.LABEL,
            defaultWidgetOptions: { area: 'left', rank: 201 },
            toggleCommandId: OPEN_RUN_INSPECTOR.id,
        });
    }
    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(OPEN_RUN_INSPECTOR, {
            execute: () => this.openView({ activate: true, reveal: true }),
        });
        commands.registerCommand(ATTACH_RUN, {
            execute: async (taskId: string) => {
                if (!taskId) {
                    return;
                }
                const widget = await this.openView({ activate: true, reveal: true });
                widget?.attachTaskId(taskId);
            },
        });
    }
    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(AQP_QUANT_VIEWS, {
            commandId: OPEN_RUN_INSPECTOR.id,
            label: RunInspectorWidget.LABEL,
            order: '2',
        });
    }
}

@injectable()
export class BacktestRunnerViewContribution extends AbstractViewContribution<BacktestRunnerWidget> {
    constructor() {
        super({
            widgetId: BacktestRunnerWidget.ID,
            widgetName: BacktestRunnerWidget.LABEL,
            defaultWidgetOptions: { area: 'left', rank: 202 },
            toggleCommandId: OPEN_BACKTEST_RUNNER.id,
        });
    }
    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(OPEN_BACKTEST_RUNNER, {
            execute: () => this.openView({ activate: true, reveal: true }),
        });
    }
    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(AQP_QUANT_VIEWS, {
            commandId: OPEN_BACKTEST_RUNNER.id,
            label: BacktestRunnerWidget.LABEL,
            order: '3',
        });
    }
}
