/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { ContainerModule } from '@theia/core/shared/inversify';

/**
 * Backend module — currently a no-op placeholder so the
 * `theiaExtensions.backend` slot in this package's package.json resolves.
 *
 * Reserved for a future static-file route that serves the bundled
 * `@finos/perspective` WASM blob from the Theia backend (rather than
 * relying on the frontend bundler to inline it). Keeping the binding
 * here so we don't have to re-edit package.json when that lands.
 */
export default new ContainerModule(_bind => {
    // Intentionally empty.
});
