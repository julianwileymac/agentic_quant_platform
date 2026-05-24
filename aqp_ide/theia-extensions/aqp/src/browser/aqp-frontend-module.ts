/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import '../../src/browser/style/index.css';

import {
    CommandContribution,
    MenuContribution,
} from '@theia/core';
import {
    FrontendApplicationContribution,
    KeybindingContribution,
    WidgetFactory,
} from '@theia/core/lib/browser';
import { ContainerModule } from '@theia/core/shared/inversify';

import { Auth0Service } from './auth/auth0-service';
import { AqpAuthService } from './auth/aqp-auth-service';
import { AqpApiService } from './aqp/aqp-api-service';
import { AqpConfigService } from './aqp/aqp-config-service';
import { AqpTenancyStore } from './aqp/aqp-tenancy-store';
import { AqpLoginContribution } from './commands/aqp-login-contribution';
import { AqpHaltContribution } from './commands/aqp-halt-contribution';
import { AqpTenancyContribution } from './commands/aqp-tenancy-contribution';
import {
    AgentRunsViewContribution,
    BotsViewContribution,
    ManagementViewContribution,
    TopologyViewContribution,
    WorkflowsViewContribution,
} from './commands/aqp-view-contributions';
import { AgentRunsWidget } from './widgets/agent-runs-widget';
import { BotsWidget } from './widgets/bots-widget';
import { ManagementWidget } from './widgets/management-widget';
import { TopologyWidget } from './widgets/topology-widget';
import { WorkflowsWidget } from './widgets/workflows-widget';

export default new ContainerModule(bind => {
    // --- Core services -----------------------------------------------------
    bind(AqpConfigService).toSelf().inSingletonScope();

    bind(Auth0Service).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(Auth0Service);

    // Management Engine BFF auth service (Phase F of aqp_management_engine).
    // Additive — Auth0Service still owns the direct PKCE login flow; this
    // service talks to AQP /auth/providers + /auth/refresh for the BFF surface.
    bind(AqpAuthService).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(AqpAuthService);

    bind(AqpTenancyStore).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(AqpTenancyStore);

    bind(AqpApiService).toSelf().inSingletonScope();

    // --- Widgets + their factories ----------------------------------------
    bind(AgentRunsWidget).toSelf();
    bind(WidgetFactory).toDynamicValue(ctx => ({
        id: AgentRunsWidget.ID,
        createWidget: () => ctx.container.get<AgentRunsWidget>(AgentRunsWidget),
    })).inSingletonScope();

    bind(WorkflowsWidget).toSelf();
    bind(WidgetFactory).toDynamicValue(ctx => ({
        id: WorkflowsWidget.ID,
        createWidget: () => ctx.container.get<WorkflowsWidget>(WorkflowsWidget),
    })).inSingletonScope();

    bind(BotsWidget).toSelf();
    bind(WidgetFactory).toDynamicValue(ctx => ({
        id: BotsWidget.ID,
        createWidget: () => ctx.container.get<BotsWidget>(BotsWidget),
    })).inSingletonScope();

    bind(TopologyWidget).toSelf();
    bind(WidgetFactory).toDynamicValue(ctx => ({
        id: TopologyWidget.ID,
        createWidget: () => ctx.container.get<TopologyWidget>(TopologyWidget),
    })).inSingletonScope();

    // Management Engine iframe widget — embeds the AQP Vite Workload Studio,
    // cluster-mgmt, and cloudflare routes inside Theia.
    bind(ManagementWidget).toSelf();
    bind(WidgetFactory).toDynamicValue(ctx => ({
        id: ManagementWidget.ID,
        createWidget: () => ctx.container.get<ManagementWidget>(ManagementWidget),
    })).inSingletonScope();

    // --- View contributions (open commands + View menu entries) -----------
    bind(AgentRunsViewContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(AgentRunsViewContribution);
    bind(MenuContribution).toService(AgentRunsViewContribution);
    bind(FrontendApplicationContribution).toService(AgentRunsViewContribution);

    bind(WorkflowsViewContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(WorkflowsViewContribution);
    bind(MenuContribution).toService(WorkflowsViewContribution);
    bind(FrontendApplicationContribution).toService(WorkflowsViewContribution);

    bind(BotsViewContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(BotsViewContribution);
    bind(MenuContribution).toService(BotsViewContribution);
    bind(FrontendApplicationContribution).toService(BotsViewContribution);

    bind(TopologyViewContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(TopologyViewContribution);
    bind(MenuContribution).toService(TopologyViewContribution);
    bind(FrontendApplicationContribution).toService(TopologyViewContribution);

    bind(ManagementViewContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(ManagementViewContribution);
    bind(MenuContribution).toService(ManagementViewContribution);
    bind(FrontendApplicationContribution).toService(ManagementViewContribution);

    // --- Login / halt / tenancy contributions -----------------------------
    bind(AqpLoginContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(AqpLoginContribution);
    bind(MenuContribution).toService(AqpLoginContribution);
    bind(FrontendApplicationContribution).toService(AqpLoginContribution);

    bind(AqpHaltContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(AqpHaltContribution);
    bind(MenuContribution).toService(AqpHaltContribution);
    bind(KeybindingContribution).toService(AqpHaltContribution);

    bind(AqpTenancyContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(AqpTenancyContribution);
    bind(MenuContribution).toService(AqpTenancyContribution);
});
