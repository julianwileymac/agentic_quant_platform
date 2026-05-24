---
name: theia-development
description: Build on the Eclipse Theia platform — authoring Theia extensions, widgets, preferences, commands/menus/keybindings, Theia AI agents, VS Code extensions for Theia, and packaging Theia Blueprint products with electron-builder. Use when working in any Theia-based monorepo, scaffolding with generator-theia-extension, composing browser/electron apps, extending the Theia IDE (Blueprint), or wiring contributions through InversifyJS dependency injection.
---

# Theia Development

Eclipse Theia is an extensible TypeScript framework for building browser-based and desktop IDEs and tools. The platform is itself a collection of Theia extensions wired together via InversifyJS dependency injection. Most development work in a Theia project falls into one of five buckets: composing an application, authoring a Theia extension, contributing widgets/commands/preferences, adding AI capabilities via Theia AI, or producing a packaged desktop product through Theia Blueprint and electron-builder.

This skill is the entry point. Skim the decision matrix and quick-start sections below, then open the matching `reference/*.md` file when you need depth.

## Decision matrix: which extension mechanism

| Mechanism | Install time | API access | Best for |
|-----------|--------------|-----------|----------|
| Theia extension | Compile time | Full Theia API via DI | New product features, custom widgets, deep integration |
| VS Code extension | Compile or runtime | VS Code Extension API only | Language support, portable features, reuse of VS Code ecosystem |
| Theia plugin | Compile or runtime | VS Code API + some Theia frontend APIs | Frontend-only Theia features; support is being phased; prefer the other two |
| Headless plugin | Runtime | Backend-only custom API | CLI workflows and backend service extensibility, no frontend |

Default rule: if VS Code's Extension API covers the feature, ship a VS Code extension. If it does not, write a Theia extension. See [reference/extensions.md](reference/extensions.md) for the full comparison.

## Project layout

A Theia application is a yarn workspaces monorepo. The Yeoman generator (`generator-theia-extension`) scaffolds the standard layout:

```
my-theia-app/
  package.json            # workspaces + lerna; build/start scripts
  hello-world/            # custom Theia extension package
    package.json          # keywords: ["theia-extension"], theiaExtensions: [...]
    src/browser/          # frontend DI module + contributions
    src/node/             # optional backend DI module
  browser-app/            # Theia application targeting browser
    package.json          # depends on @theia/* extensions + custom extension
  electron-app/           # Theia application targeting Electron
    package.json
```

Scaffold a new project with:

```bash
npm install -g yo generator-theia-extension
mkdir my-theia-app && cd my-theia-app
yo theia-extension     # pick Hello World / Widget / Backend / VSCode / AI
```

See [reference/build-and-run.md](reference/build-and-run.md) for the full build pipeline.

## Dependency injection basics

Theia uses InversifyJS. Every contribution is an `@injectable()` class bound in a `ContainerModule` that the application aggregates at startup. The `theiaExtensions` array in `package.json` points the framework at the DI module files:

```json
"theiaExtensions": [
  { "frontend": "lib/browser/hello-world-frontend-module" },
  { "backend":  "lib/node/hello-world-backend-module" }
]
```

A minimal frontend module:

```typescript
import { ContainerModule } from '@theia/core/shared/inversify';
import { CommandContribution, MenuContribution } from '@theia/core';
import { HelloWorldCommandContribution, HelloWorldMenuContribution } from './hello-world-contribution';

export default new ContainerModule(bind => {
    bind(CommandContribution).to(HelloWorldCommandContribution);
    bind(MenuContribution).to(HelloWorldMenuContribution);
});
```

Inject dependencies via constructor parameters or fields:

```typescript
constructor(@inject(MessageService) private readonly messageService: MessageService) {}
```

For contribution-point details and `bindContributionProvider`, see [reference/architecture.md](reference/architecture.md).

## Commands, menus, keybindings

Implement `CommandContribution`, `MenuContribution`, and `KeybindingContribution`. The command ID is the linchpin connecting all three. See `templates/command-contribution.ts.md` for a ready-to-paste snippet.

```typescript
export const HelloWorldCommand: Command = { id: 'hello.command', label: 'Say Hello' };

@injectable()
export class HelloWorldCommandContribution implements CommandContribution {
    constructor(@inject(MessageService) private readonly messageService: MessageService) {}
    registerCommands(registry: CommandRegistry): void {
        registry.registerCommand(HelloWorldCommand, {
            execute: () => this.messageService.info('Hello World!')
        });
    }
}
```

Menus use a `MenuPath` (often from `CommonMenus`):

```typescript
menus.registerMenuAction(CommonMenus.EDIT_FIND, {
    commandId: HelloWorldCommand.id,
    label: HelloWorldCommand.label
});
```

Keybindings support VS Code-style `when` clauses and platform-independent modifiers (`ctrlcmd`).

## Widgets

A widget is a workbench-managed UI surface (view, editor, panel). Choose the right base class:

- `ReactWidget` — most custom views; render React in `render()`
- `TreeWidget` — tree views with built-in selection/expansion
- `BaseWidget` — non-React custom DOM

Three pieces wire a widget into Theia: the widget class, a `WidgetFactory` binding, and an `AbstractViewContribution` that registers the open-view command and menu entry. See `templates/widget-contribution.tsx.md` and [reference/widgets.md](reference/widgets.md).

## Preferences

Define a `PreferenceSchema`, register it via `PreferenceContribution`, and optionally expose it through a `PreferenceProxy` for type safety. Scopes (Default → User → Workspace → Folder) determine where users can set a value; resolution always walks from most specific to most general. Backend preferences are supported since 1.65 but only see Default and User scopes.

```typescript
export const myPrefsSchema: PreferenceSchema = {
    properties: {
        'myExt.timeout': { type: 'number', default: 5000, scope: PreferenceScope.Workspace }
    }
};
```

See `templates/preference-schema.ts.md` and [reference/preferences.md](reference/preferences.md).

## Theia AI

Theia AI ships with the platform and adds Agents, prompt fragments, variables, tool functions, response part renderers, change sets, slash commands, modes, and capabilities. A minimal chat agent extends `AbstractStreamParsingChatAgent`, declares `languageModelRequirements`, and is bound to both `Agent` and `ChatAgent`:

```typescript
export class CommandChatAgent extends AbstractStreamParsingChatAgent {
    id = 'Command';
    name = 'Command';
    description = 'Helps users find and execute commands';
    languageModelRequirements: LanguageModelRequirement[] = [{ purpose: 'chat', identifier: 'default/universal' }];
    protected defaultLanguageModelPurpose = 'chat';
    override prompts = [{ id: commandPromptTemplate.id, defaultVariant: commandPromptTemplate }];
    protected override systemPromptId = commandPromptTemplate.id;
}
```

```typescript
bind(Agent).toService(CommandChatAgent);
bind(ChatAgent).toService(CommandChatAgent);
```

Tool functions implement `ToolProvider`; global variables implement `AIVariableContribution` and register with `AIVariableService`. For deep coverage of variables, tool functions, response renderers, change sets, GitHub Copilot integration, and custom LLM providers, see [reference/theia-ai.md](reference/theia-ai.md) and `templates/chat-agent.ts.md`.

## Build and run

This repository's root scripts (from `package.json`) are:

```bash
yarn                            # install + patch postinstall hooks
yarn build:extensions           # compile extension packages
yarn build:applications:dev     # dev build for browser/electron apps
yarn build:applications         # production app build
yarn browser start              # serve browser app at http://localhost:3000
yarn electron package:preview   # package preview for desktop validation
```

Under the hood, the Theia CLI does the heavy lifting (`theia build`,
`theia rebuild:browser`, `theia start`). When you change native dependencies or
switch between browser and electron targets, rerun the matching rebuild path.
See [reference/build-and-run.md](reference/build-and-run.md) for proxy-aware
native builds and lerna details.

## Theia Blueprint (the Theia IDE) and packaging

Theia Blueprint is the reference desktop product built on Theia. Use it as a template when you want installers, branding, and auto-update. Add your extension by dropping it into `theia-extensions/<name>/`, listing it as a dependency in `applications/electron/package.json` (and `applications/browser/package.json` if applicable), and running `yarn && yarn build`.

Customize:
- Application name: `theia.frontend.config.applicationName` in `applications/electron/package.json`
- Icons: `applications/electron/resources/` (`icon.ico`, `icons.icns`, `icons/` for Linux)
- Welcome page: rebind `WidgetFactory` for `GettingStartedWidget`
- About dialog: rebind `AboutDialog`
- Splash screen: `theia.frontend.config.electron.splashScreenOptions`

Packaging targets via electron-builder (`applications/electron/electron-builder.yml`):
- Windows: `nsis` installer, AppX, MSI, portable
- macOS: `dmg`, `pkg`, `mas`
- Linux: `AppImage`, `deb`, `rpm`, `snap`

```bash
yarn electron package          # full installer for current OS
yarn electron package:preview  # unpackaged tree only
yarn electron deploy           # publish
```

For signing, auto-update, white-labeling, and OS-specific installer options, see [reference/blueprint-packaging.md](reference/blueprint-packaging.md).

## Working checklist

When adding a feature, follow this order:

1. Decide the mechanism: VS Code extension first, Theia extension if you need full API access.
2. Scaffold or locate the package; confirm `keywords: ["theia-extension"]` and `theiaExtensions` are set.
3. Implement `@injectable()` contribution classes.
4. Bind them in the frontend or backend `ContainerModule` (the file referenced by `theiaExtensions`).
5. Add the package to `dependencies` of the consuming application (`browser-app`, `electron-app`, or Blueprint's `applications/*`).
6. Run `yarn`, `yarn build:extensions`, and `yarn build:applications:dev`, then
   start the target (`yarn browser start` or `yarn electron start`) and
   exercise the feature.
7. If publishing: bump versions, run `yarn electron package` for installers.

## Reference files

Open these for depth on the matching topic — they are intentionally one level deep so the load path stays predictable:

- [reference/architecture.md](reference/architecture.md) — frontend/backend processes, DI container assembly, contribution providers
- [reference/extensions.md](reference/extensions.md) — full comparison of the four extension mechanisms
- [reference/widgets.md](reference/widgets.md) — widget base classes, factories, lifecycle, view contributions
- [reference/preferences.md](reference/preferences.md) — schema, scopes, proxies, backend usage, advanced features
- [reference/theia-ai.md](reference/theia-ai.md) — chat agents, variables, tool functions, response renderers, change sets, modes, capabilities, LLM providers
- [reference/blueprint-packaging.md](reference/blueprint-packaging.md) — Blueprint customization, electron-builder, signing, auto-update
- [reference/build-and-run.md](reference/build-and-run.md) — yarn/lerna scripts, Theia CLI, native dependencies

## Templates

Copy-paste boilerplate from the `templates/` folder:

- `templates/command-contribution.ts.md`
- `templates/widget-contribution.tsx.md`
- `templates/preference-schema.ts.md`
- `templates/chat-agent.ts.md`
- `templates/extension-package.json.md`

## Conventions

- Always confirm the `@theia/core` version in the consuming application's `package.json` and align your extension's `@theia/*` dependencies to it.
- Frontend code lives under `src/browser/`, backend code under `src/node/`, shared code under `src/common/`.
- Bind contributions by their public symbol (e.g. `bind(CommandContribution).to(MyContribution)`), not by concrete class.
- Avoid direct DOM access in widgets — prefer the React render flow or Theia's existing widget services.
- Keep extension package names unique and version them with semver; Theia uses `^` ranges aggressively across the platform.
