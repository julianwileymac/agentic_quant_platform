# Theia Architecture

Theia is a modular framework whose entire surface — including the platform itself — is built from Theia extensions. The architecture has two cooperating processes (a frontend in the browser/Electron renderer and a backend in Node) and a dependency injection container in each that aggregates contributions from every extension at startup.

## Processes

| Process | Runs in | Role |
|---------|---------|------|
| Frontend | Browser tab or Electron renderer | UI, workbench layout, widgets, command/menu execution |
| Backend | Node.js | Filesystem, processes, language servers, terminals, plugin host |

The frontend talks to the backend over JSON-RPC channels (`@theia/core`'s `MessagingContribution`). When you contribute a backend service that the frontend should use, expose it through a `ConnectionHandler` (RPC) and inject a generated proxy on the frontend.

## DI containers

Each process owns a single global InversifyJS container. The container is built by aggregating one `ContainerModule` per extension entry point. Extensions declare entry points in `theiaExtensions`:

```json
"theiaExtensions": [
  { "frontend": "lib/browser/my-extension-frontend-module",
    "backend":  "lib/node/my-extension-backend-module" }
]
```

Each module exports a default `ContainerModule` whose `bind` callback registers contributions:

```typescript
export default new ContainerModule(bind => {
    bind(CommandContribution).to(MyCommandContribution);
    bind(MenuContribution).to(MyMenuContribution);
});
```

Theia recommends binding by interface (a `Symbol` with the same name as the interface). Consumers `@inject` the same symbol and the container returns the bound implementation.

## Injection sites

```typescript
// Constructor injection
constructor(@inject(MessageService) private readonly messageService: MessageService) {}

// Field injection
@inject(MessageService)
protected readonly messageService!: MessageService;

// Initialisation hook (after construction and field injection)
@postConstruct()
protected init(): void { ... }
```

Only classes annotated with `@injectable()` and registered in the container can be injected. Use field injection for optional collaborators and constructor injection for required ones.

## Contribution points

A contribution point is an interface that any extension can implement to plug into a piece of behaviour. The Theia platform defines many: `CommandContribution`, `MenuContribution`, `KeybindingContribution`, `PreferenceContribution`, `WidgetFactory`, `OpenHandler`, `ConnectionHandler`, `BackendApplicationContribution`, `FrontendApplicationContribution`, `LabelProviderContribution`, `Agent`, `ChatAgent`, `ToolProvider`, `AIVariableContribution`, and so on. Search the Theia source for interfaces named `*Contribution` to enumerate them.

To implement one:

1. Write an `@injectable()` class implementing the contribution interface.
2. Bind it in your `ContainerModule`: `bind(CommandContribution).to(MyCommandContribution)`.
3. The framework injects a `ContributionProvider<CommandContribution>` wherever the platform consumes them, iterates, and calls the well-known method (e.g. `registerCommands`).

## Defining your own contribution point

When your extension needs others to plug in, define an interface and use `bindContributionProvider`:

```typescript
import { bindContributionProvider, ContributionProvider } from '@theia/core';

export const MyHook = Symbol('MyHook');
export interface MyHook { onSomething(): void; }

export default new ContainerModule(bind => {
    bindContributionProvider(bind, MyHook);
});

@injectable()
export class MyService {
    constructor(@inject(ContributionProvider) @named(MyHook)
                private readonly hooks: ContributionProvider<MyHook>) {}
    fire(): void { for (const h of this.hooks.getContributions()) h.onSomething(); }
}
```

Other extensions then bind their `MyHook` implementations and the platform routes them in automatically.

## Lifecycle contributions

- `FrontendApplicationContribution` — `onStart`, `onStop`, `initialize`, `configure`; called by the application shell during the frontend lifecycle.
- `BackendApplicationContribution` — `onStart`, `onStop`, `configure`; called on the Node backend.
- `ConnectionHandler` — registers an RPC channel; combined with `JsonRpcConnectionHandler` to expose a service to the frontend.

Use these when your extension needs initialisation, background work, or to register RPC services rather than respond to user actions.

## Frontend ↔ backend communication

A common pattern: expose a backend service to the frontend via RPC.

```typescript
// common/my-service.ts
export const MyService = Symbol('MyService');
export interface MyService { doWork(input: string): Promise<string>; }
export const myServicePath = '/services/my-service';

// node/my-backend-module.ts
import { ConnectionHandler, JsonRpcConnectionHandler } from '@theia/core';
export default new ContainerModule(bind => {
    bind(MyService).to(MyServiceImpl).inSingletonScope();
    bind(ConnectionHandler).toDynamicValue(ctx =>
        new JsonRpcConnectionHandler(myServicePath, () => ctx.container.get(MyService))
    ).inSingletonScope();
});

// browser/my-frontend-module.ts
import { WebSocketConnectionProvider } from '@theia/core/lib/browser';
export default new ContainerModule(bind => {
    bind(MyService).toDynamicValue(ctx => {
        const provider = ctx.container.get(WebSocketConnectionProvider);
        return provider.createProxy<MyService>(myServicePath);
    }).inSingletonScope();
});
```

The frontend now injects `MyService` and calls it like a normal service — the proxy handles transport.

## Rebinding

To replace a default platform service, use `rebind` inside your `ContainerModule`:

```typescript
isBound(AboutDialog)
    ? rebind(AboutDialog).to(MyAboutDialog).inSingletonScope()
    : bind(AboutDialog).to(MyAboutDialog).inSingletonScope();
```

The `isBound` guard prevents errors when your module is loaded before the platform module that provides the default.

## Project structure inside an extension

```
my-extension/
  package.json
  src/
    common/                 # shared interfaces + symbols + RPC paths
    browser/
      my-frontend-module.ts # default-exported ContainerModule
      my-contribution.ts    # @injectable() classes
    node/
      my-backend-module.ts
      my-service-impl.ts
  tsconfig.json
```

`package.json` points `theiaExtensions[].frontend` and `theiaExtensions[].backend` at the compiled module files under `lib/`. The `prepare` script runs `tsc` so consumers always see compiled output.

## Tips

- Prefer `inSingletonScope()` for stateful services so the container does not instantiate them per injection.
- Use `@postConstruct()` for setup that needs other injected fields — constructor parameters are still being resolved at construction time.
- When in doubt, search the Theia source for an existing contribution that does what you need and mirror its binding style.
