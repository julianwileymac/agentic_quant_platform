/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { ILogger } from '@theia/core';
import { FrontendApplicationContribution } from '@theia/core/lib/browser';
import { inject, injectable } from '@theia/core/shared/inversify';

import {
    AQP_PERSPECTIVE_ARROW_MIME,
    AQP_PERSPECTIVE_ARROW_RENDERER_ID,
} from '../../common/aqp-notebook-protocol';

/**
 * Notebook output that arrives at this renderer. Theia's
 * `NotebookCellOutputItem` shape (mirrors VS Code's `NotebookCellOutputItem`):
 * a MIME type string + raw bytes (`Uint8Array`).
 */
export interface AqpRendererOutputItem {
    readonly mime: string;
    readonly data: Uint8Array;
}

/**
 * Subset of the `<perspective-viewer>` Custom Element API we depend on.
 * Re-declared so this file does not need a hard `@finos/perspective`
 * type dependency at compile time — the package is bundled into the
 * frontend app and loaded lazily at runtime.
 */
interface PerspectiveViewerElement extends HTMLElement {
    load(table: unknown): Promise<void>;
    restore(config: object): Promise<void>;
}

/**
 * MIME renderer for `application/vnd.aqp.perspective-arrow+arrow`. Mounts
 * a `<perspective-viewer>` Custom Element into the notebook output area
 * and pushes Arrow record batches straight into Perspective's WASM engine.
 *
 * Loading strategy:
 *
 *  - The first time a Perspective MIME output is rendered, we lazy-load
 *    `@finos/perspective` and `@finos/perspective-viewer-datagrid` via
 *    dynamic `import()`. This keeps the cold-start bundle small and
 *    matches Theia's pattern for `@theia/ai-mcp-ui` (lazy-loaded MCP
 *    panel).
 *  - If the dynamic import fails (e.g. the bundle did not include
 *    `@finos/perspective`), the renderer falls back to a textual
 *    Arrow preview that shows the number of bytes received plus the
 *    MIME type — operators always see something useful.
 *
 * The renderer NEVER issues HTTP requests of its own — every Arrow batch
 * arrives from the kernel via the notebook output channel.
 */
@injectable()
export class PerspectiveArrowRenderer implements FrontendApplicationContribution {

    @inject(ILogger)
    protected readonly logger!: ILogger;

    // Typed as `unknown` because `@finos/perspective`'s shipped type
    // declarations are not browser-target compatible at the TS 4.9 level
    // used by this extension. We dynamic-import and cast at the call site.
    protected perspectivePromise?: Promise<unknown>;

    readonly id = AQP_PERSPECTIVE_ARROW_RENDERER_ID;
    readonly mimeTypes = [AQP_PERSPECTIVE_ARROW_MIME];

    async onStart(): Promise<void> {
        // Theia 1.65+ does not (yet) expose a public NotebookRendererRegistry
        // singleton from `@theia/notebook`. The canonical way to register a
        // notebook renderer is the `contributes.notebookRenderers` entry in
        // a VS Code extension manifest, OR (Theia-internal) via
        // `NotebookRendererRegistry.registerRenderer`.
        //
        // We try the internal registry first (compile-time pathway used by
        // this extension). If the registry is unavailable, we log a clear
        // operator message and rely on the manifest-style fallback emitted
        // by the `aqp.notebook.helpers` Python helpers (which can include
        // their own VS Code-extension-style renderer asset).
        try {
            const registry = await this.resolveRegistry();
            if (!registry) {
                this.logger.warn(
                    '[aqp-notebook-quant] Notebook renderer registry not available. ' +
                    'Perspective Arrow outputs will fall back to a textual preview.'
                );
                return;
            }
            registry.registerRenderer({
                id: this.id,
                displayName: 'AQP Perspective Arrow',
                mimeTypes: this.mimeTypes,
                entrypoint: () => this.render.bind(this),
            });
        } catch (err) {
            this.logger.error(
                '[aqp-notebook-quant] Failed to register Perspective Arrow renderer:',
                err instanceof Error ? err.message : err,
            );
        }
    }

    /**
     * Renders a single AQP Perspective Arrow output into the supplied
     * container element. Public so unit tests can drive it directly.
     */
    async render(container: HTMLElement, output: AqpRendererOutputItem): Promise<void> {
        if (output.mime !== AQP_PERSPECTIVE_ARROW_MIME) {
            return;
        }
        const perspective = await this.loadPerspective();
        if (!perspective) {
            container.innerHTML = '';
            const fallback = document.createElement('pre');
            fallback.className = 'aqp-perspective-fallback';
            fallback.textContent =
                `[AQP Perspective] @finos/perspective not bundled. ` +
                `Received ${output.data.byteLength} Arrow bytes. ` +
                `Install @finos/perspective in applications/browser/package.json to enable the grid.`;
            container.appendChild(fallback);
            return;
        }

        container.innerHTML = '';
        const viewer = document.createElement('perspective-viewer') as PerspectiveViewerElement;
        viewer.style.width = '100%';
        viewer.style.height = '420px';
        container.appendChild(viewer);

        try {
            const worker = (perspective as { worker(): { table(bytes: ArrayBuffer): Promise<unknown> } }).worker();
            const table = await worker.table(output.data.buffer);
            await viewer.load(table);
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this.logger.warn('[aqp-notebook-quant] Perspective load failed:', message);
            viewer.innerHTML = `<pre class="aqp-perspective-error">Perspective load failed: ${message}</pre>`;
        }
    }

    protected async loadPerspective(): Promise<unknown | undefined> {
        if (this.perspectivePromise) {
            return this.perspectivePromise;
        }
        this.perspectivePromise = (async () => {
            try {
                // Lazy import so first-render cost is only paid when a Perspective
                // MIME output actually arrives. The two viewer plugins are loaded
                // for their side effects — registering the datagrid and d3fc
                // renderer plugins with the Perspective viewer registry. The
                // dynamic specifier + cast keep this typecheck-clean at TS 4.9
                // even though @finos/perspective's d.ts files are esm-only.
                const perspectiveSpecifier = '@finos/perspective' as string;
                const datagridSpecifier = '@finos/perspective-viewer-datagrid' as string;
                const d3fcSpecifier = '@finos/perspective-viewer-d3fc' as string;
                const dynImport = (s: string) => (Function('s', 'return import(s)') as (s: string) => Promise<unknown>)(s);
                const [mod] = await Promise.all([
                    dynImport(perspectiveSpecifier),
                    dynImport(datagridSpecifier).catch(() => undefined),
                    dynImport(d3fcSpecifier).catch(() => undefined),
                ]);
                return mod;
            } catch (err) {
                this.logger.warn(
                    '[aqp-notebook-quant] @finos/perspective dynamic import failed; falling back to text:',
                    err instanceof Error ? err.message : err,
                );
                return undefined;
            }
        })();
        return this.perspectivePromise;
    }

    protected async resolveRegistry(): Promise<RendererRegistryLike | undefined> {
        // Resolved via dynamic `require` so that builds that strip
        // `@theia/notebook` do not fail the entire extension boot.
        try {
            const mod = await import('@theia/notebook/lib/browser/notebook-renderer-registry').catch(() => undefined);
            const registry = (mod as { NotebookRendererRegistry?: { instance?: RendererRegistryLike } } | undefined)
                ?.NotebookRendererRegistry?.instance;
            return registry;
        } catch {
            return undefined;
        }
    }
}

interface RendererRegistryLike {
    registerRenderer(info: {
        id: string;
        displayName: string;
        mimeTypes: readonly string[];
        entrypoint: () => (container: HTMLElement, output: AqpRendererOutputItem) => Promise<void>;
    }): void;
}
