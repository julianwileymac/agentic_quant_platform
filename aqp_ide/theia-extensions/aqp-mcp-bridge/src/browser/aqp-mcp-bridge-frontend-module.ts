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

import { AqpMcpContribution } from './commands/aqp-mcp-contribution';
import { AqpMcpRegistrar } from './mcp/aqp-mcp-registrar';

/**
 * Wires the MCP registrar + command surface into the Theia frontend
 * container. Loaded as a compile-time extension via the `theiaExtensions`
 * entry in this package's package.json.
 */
export default new ContainerModule(bind => {
    bind(AqpMcpRegistrar).toSelf().inSingletonScope();
    bind(FrontendApplicationContribution).toService(AqpMcpRegistrar);

    bind(AqpMcpContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(AqpMcpContribution);
    bind(MenuContribution).toService(AqpMcpContribution);
});
