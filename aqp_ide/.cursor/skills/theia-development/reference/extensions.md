# Extension Mechanisms

Theia supports four complementary ways to extend a tool. Pick the one that gives you the smallest API surface that still meets the requirement. You can — and frequently should — combine more than one in the same product.

## Theia extensions

- Install time: compile time (added as an npm dependency of the application).
- API surface: the entire Theia API via dependency injection. Can rebind core services.
- Where they run: in the same processes as the host application (frontend, backend, or both).
- Identified by: `keywords: ["theia-extension"]` and a `theiaExtensions` array in `package.json`.
- Use for: new widgets, custom workbenches, deep replacements of built-in services, anything the VS Code API cannot express.

Authoring sketch:

```json
{
  "name": "my-extension",
  "keywords": ["theia-extension"],
  "dependencies": { "@theia/core": "latest" },
  "theiaExtensions": [
    { "frontend": "lib/browser/my-extension-frontend-module",
      "backend":  "lib/node/my-extension-backend-module" }
  ]
}
```

The exported `default ContainerModule` in each module file is merged into the application's global container at startup.

## VS Code extensions

- Install time: compile time (bundled) or runtime (installed by users).
- API surface: the VS Code Extension API only.
- Where they run: in a per-frontend extension host (separate process), sandboxed.
- Identified by: a standard VS Code `package.json` with `engines.vscode`.
- Use for: language support, themes, snippets, anything portable that should also work in VS Code.

Theia provides the same Extension API as VS Code, so most extensions install unmodified. The marketplace is [Open VSX](https://open-vsx.org/) by default; point at a private registry by setting `VSX_REGISTRY_URL` on the backend.

Bundle built-in VS Code extensions via the `theiaPlugins` map in the consuming application's `package.json`:

```json
"theiaPlugins": {
  "redhat.vscode-yaml": "https://open-vsx.org/api/redhat/vscode-yaml/1.14.0/file/redhat.vscode-yaml-1.14.0.vsix"
}
```

`yarn install`, `yarn prepare`, or `yarn download:plugins` downloads them into `applications/<target>/plugins/`. Remove an entry to drop the extension; clean the folder if you need to fully re-download.

For VS Code API coverage in Theia, consult the [coverage report](https://eclipse-theia.github.io/vscode-theia-comparator/status.html).

## Theia plugins

- Install time: compile time or runtime.
- API surface: the VS Code API plus a few Theia-only frontend APIs.
- Where they run: in a per-frontend plugin host like VS Code extensions, but with frontend-side hooks not available in VS Code.
- Status: support is being phased out. Prefer VS Code extensions or Theia extensions for new work.

If you encounter an existing Theia plugin, treat it as a VS Code extension with extra Theia-specific imports.

## Headless plugins

- Install time: runtime.
- API surface: backend-only custom API exposed explicitly by the application.
- Where they run: in a dedicated Node process not tied to any frontend connection.
- Use for: CLI integrations, headless automation, server-only extensibility.

Headless plugins do not have direct access to standard Theia backend services. The application defines its own headless plugin API and the plugin host injects it. This is the right tool for scripted workflows and headless deployments.

## How to choose

Walk the questions in order:

1. Does the feature target the frontend only and is it covered by the VS Code Extension API? → VS Code extension.
2. Does it need direct access to internal Theia services, custom contribution points, or replacement of built-in services? → Theia extension.
3. Is it a backend-only workflow with no frontend? → Headless plugin.
4. Otherwise, default to Theia extension.

If you start with a VS Code extension and outgrow the API, you can wrap it in a Theia extension that exposes the missing capability via a Theia plugin API surface or a custom service — but the cleanest path is usually to migrate the relevant logic into a Theia extension.

## Mixing mechanisms

A real product blends them:

- VS Code extensions for language servers, themes, and ecosystem features.
- Theia extensions for the product's unique workbench, branding, custom widgets, AI agents, and replacements of welcome page or About dialog.
- Headless plugins (where used) for batch jobs.

Each is added independently to `applications/<target>/package.json`. The application builds all of them into one product at compile time.

## Version compatibility

Always check your extension's `@theia/core` (and other `@theia/*`) versions against the version used by the consuming application. The Theia API evolves quickly; even minor versions can change service signatures. When integrating a Yeoman-generated extension into Blueprint, update `@theia/*` dependencies to match Blueprint's lockfile first.

## Distribution

- Compile-time inclusion: declare the extension as a dependency in `browser-app`/`electron-app`/Blueprint's `applications/*/package.json` and rely on `yarn` linking. Inside a monorepo, this picks up the local copy.
- npm publish: `yarn publish` after bumping the version. Consumers add it like any other dependency.
- Built-in VS Code extensions: `theiaPlugins` map (vsix URL).
- Runtime VS Code extensions: enable Open VSX integration; users install through the Extensions view.

See `blueprint-packaging.md` for productization steps and `build-and-run.md` for build pipeline details.
