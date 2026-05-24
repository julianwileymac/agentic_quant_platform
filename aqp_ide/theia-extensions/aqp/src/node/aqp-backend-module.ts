/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { BackendApplicationContribution } from '@theia/core/lib/node/backend-application';
import { ContainerModule } from '@theia/core/shared/inversify';

import { AqpConfigEndpoint } from './aqp-config-endpoint';

export default new ContainerModule(bind => {
    bind(AqpConfigEndpoint).toSelf().inSingletonScope();
    bind(BackendApplicationContribution).toService(AqpConfigEndpoint);
});
