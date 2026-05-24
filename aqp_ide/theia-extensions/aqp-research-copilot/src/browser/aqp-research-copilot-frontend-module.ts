/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { ContainerModule } from '@theia/core/shared/inversify';

import { AqpResearchAgent } from './copilot/aqp-research-agent';
import { AqpToolRegistry } from './copilot/aqp-tool-functions';
import { RouterCompleteClient } from './copilot/router-complete-client';

/**
 * Wires the AQP Research Copilot's three services into the Theia frontend
 * container.
 *
 * `AqpResearchAgent` is bound to itself; we do NOT bind it to the
 * `@theia/ai-core` `Agent` symbol here because doing so requires the AI
 * core package to be present and would cause a hard build dependency. The
 * AGENT registration happens inside `AqpResearchAgent.onStart` via dynamic
 * `AgentService` lookup — it gracefully no-ops when the AI core service
 * is not bound.
 */
export default new ContainerModule(bind => {
    bind(RouterCompleteClient).toSelf().inSingletonScope();
    bind(AqpToolRegistry).toSelf().inSingletonScope();
    bind(AqpResearchAgent).toSelf().inSingletonScope();
});
