/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { AbstractViewContribution, CommonMenus } from '@theia/core/lib/browser';
import { Command, CommandRegistry, MenuModelRegistry, MenuPath } from '@theia/core';
import { injectable } from '@theia/core/shared/inversify';

import { AgentRunsWidget } from '../widgets/agent-runs-widget';
import { BotsWidget } from '../widgets/bots-widget';
import { ManagementWidget } from '../widgets/management-widget';
import { TopologyWidget } from '../widgets/topology-widget';
import { WorkflowsWidget } from '../widgets/workflows-widget';
import { AqpCommandIds } from '../../common/aqp-protocol';

/**
 * The four view contributions register their widgets as left-panel views,
 * own a `aqp.open*` command each, and feed a shared "View -> AQP" submenu.
 *
 * The pattern (AbstractViewContribution + WidgetFactory) is the canonical
 * Theia approach for sidebar views; see
 * [.cursor/skills/theia-development/templates/widget-contribution.tsx.md].
 */

export const AQP_CATEGORY = 'AQP';

export namespace AqpMenus {
    export const AQP_VIEWS: MenuPath = [...CommonMenus.VIEW_VIEWS, 'aqp'];
}

const OPEN_AGENT_RUNS: Command = {
    id: AqpCommandIds.OPEN_AGENTS,
    category: AQP_CATEGORY,
    label: 'Show Agent Runs',
};

const OPEN_WORKFLOWS: Command = {
    id: AqpCommandIds.OPEN_WORKFLOWS,
    category: AQP_CATEGORY,
    label: 'Show Workflows',
};

const OPEN_BOTS: Command = {
    id: AqpCommandIds.OPEN_BOTS,
    category: AQP_CATEGORY,
    label: 'Show Bots',
};

const OPEN_TOPOLOGY: Command = {
    id: AqpCommandIds.OPEN_TOPOLOGY,
    category: AQP_CATEGORY,
    label: 'Show Topology',
};

const OPEN_MANAGEMENT: Command = {
    id: AqpCommandIds.OPEN_MANAGEMENT,
    category: AQP_CATEGORY,
    label: 'Show Management Engine',
};

@injectable()
export class AgentRunsViewContribution extends AbstractViewContribution<AgentRunsWidget> {
    constructor() {
        super({
            widgetId: AgentRunsWidget.ID,
            widgetName: AgentRunsWidget.LABEL,
            defaultWidgetOptions: { area: 'left', rank: 100 },
            toggleCommandId: OPEN_AGENT_RUNS.id,
        });
    }
    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(OPEN_AGENT_RUNS, {
            execute: () => this.openView({ activate: true, reveal: true }),
        });
    }
    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(AqpMenus.AQP_VIEWS, {
            commandId: OPEN_AGENT_RUNS.id,
            label: AgentRunsWidget.LABEL,
            order: '1',
        });
    }
}

@injectable()
export class WorkflowsViewContribution extends AbstractViewContribution<WorkflowsWidget> {
    constructor() {
        super({
            widgetId: WorkflowsWidget.ID,
            widgetName: WorkflowsWidget.LABEL,
            defaultWidgetOptions: { area: 'left', rank: 101 },
            toggleCommandId: OPEN_WORKFLOWS.id,
        });
    }
    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(OPEN_WORKFLOWS, {
            execute: () => this.openView({ activate: true, reveal: true }),
        });
    }
    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(AqpMenus.AQP_VIEWS, {
            commandId: OPEN_WORKFLOWS.id,
            label: WorkflowsWidget.LABEL,
            order: '2',
        });
    }
}

@injectable()
export class BotsViewContribution extends AbstractViewContribution<BotsWidget> {
    constructor() {
        super({
            widgetId: BotsWidget.ID,
            widgetName: BotsWidget.LABEL,
            defaultWidgetOptions: { area: 'left', rank: 102 },
            toggleCommandId: OPEN_BOTS.id,
        });
    }
    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(OPEN_BOTS, {
            execute: () => this.openView({ activate: true, reveal: true }),
        });
    }
    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(AqpMenus.AQP_VIEWS, {
            commandId: OPEN_BOTS.id,
            label: BotsWidget.LABEL,
            order: '3',
        });
    }
}

@injectable()
export class TopologyViewContribution extends AbstractViewContribution<TopologyWidget> {
    constructor() {
        super({
            widgetId: TopologyWidget.ID,
            widgetName: TopologyWidget.LABEL,
            defaultWidgetOptions: { area: 'left', rank: 103 },
            toggleCommandId: OPEN_TOPOLOGY.id,
        });
    }
    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(OPEN_TOPOLOGY, {
            execute: () => this.openView({ activate: true, reveal: true }),
        });
    }
    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(AqpMenus.AQP_VIEWS, {
            commandId: OPEN_TOPOLOGY.id,
            label: TopologyWidget.LABEL,
            order: '4',
        });
    }
}

@injectable()
export class ManagementViewContribution extends AbstractViewContribution<ManagementWidget> {
    constructor() {
        super({
            widgetId: ManagementWidget.ID,
            widgetName: ManagementWidget.LABEL,
            // Embedded iframe wants horizontal real estate — open in the
            // main area instead of the narrow left panel.
            defaultWidgetOptions: { area: 'main', rank: 104 },
            toggleCommandId: OPEN_MANAGEMENT.id,
        });
    }
    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(OPEN_MANAGEMENT, {
            execute: () => this.openView({ activate: true, reveal: true }),
        });
    }
    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(AqpMenus.AQP_VIEWS, {
            commandId: OPEN_MANAGEMENT.id,
            label: ManagementWidget.LABEL,
            order: '5',
        });
    }
}
