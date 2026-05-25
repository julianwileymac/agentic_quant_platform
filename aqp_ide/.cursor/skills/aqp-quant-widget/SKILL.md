---
name: aqp-quant-widget
description: Step-by-step skill for adding a new AQP quant widget to `theia-extensions/aqp-quant/` (or a sibling AQP extension). Covers scaffolding, view contribution, Auth0 gating, canonical progress frame, and docs.
---

# Add a new AQP quant widget

Use this skill when adding a new operator-facing widget inside the AQP
IDE — typically into `theia-extensions/aqp-quant/`, occasionally into a
new sibling extension when the widget doesn't fit the spec/run/backtest
theme.

## Pre-flight

- Confirm the widget complements, not duplicates, the AQP Vite
  operator UI (`aqp_client/`).
- Confirm the widget surfaces an AQP REST endpoint that already exists
  — never invent a new endpoint here (that's the AQP monolith's job).
- If the widget needs WebSocket streaming, plan to subscribe via the
  canonical `{task_id, stage, message, timestamp, **extras}` progress
  frame (AQP rule 4).

## Step 1 — Pick the home extension

Default: `theia-extensions/aqp-quant/`. Use a sibling only when the
widget is conceptually distinct (e.g. a new `aqp-trading-ext` for an
order blotter).

## Step 2 — Author the widget class

Create `src/browser/widgets/<name>-widget.tsx`. Subclass
`AqpWidgetBase` (from `theia-ide-aqp-ext`). Follow
`spec-author-widget.tsx` as the canonical reference.

Required boilerplate:

```typescript
@injectable()
export class MyNewWidget extends AqpWidgetBase {
    static readonly ID = 'aqp.quant.view.my-new';
    static readonly LABEL = 'AQP: My New Widget';

    @postConstruct()
    protected init(): void {
        this.id = MyNewWidget.ID;
        this.title.label = MyNewWidget.LABEL;
        this.title.caption = MyNewWidget.LABEL;
        this.title.closable = true;
        this.title.iconClass = 'codicon codicon-<icon>';
        this.setupSubscriptions();
        if (this.authState.isAuthenticated) {
            this.refresh();
        }
        this.update();
    }

    protected renderBody(): React.ReactNode {
        // ... only runs once authState.isAuthenticated is true
    }
}
```

## Step 3 — Add the view id + command id

Add to `src/common/aqp-quant-protocol.ts`:

```typescript
export namespace AqpQuantViewIds {
    export const MY_NEW = 'aqp.quant.view.my-new';
}
export namespace AqpQuantCommandIds {
    export const OPEN_MY_NEW = 'aqp.quant.openMyNew';
}
```

## Step 4 — Add the view contribution

In `src/browser/commands/aqp-quant-view-contributions.ts`:

```typescript
@injectable()
export class MyNewViewContribution extends AbstractViewContribution<MyNewWidget> {
    constructor() {
        super({
            widgetId: MyNewWidget.ID,
            widgetName: MyNewWidget.LABEL,
            defaultWidgetOptions: { area: 'left', rank: 210 },
            toggleCommandId: AqpQuantCommandIds.OPEN_MY_NEW,
        });
    }
    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand({ id: AqpQuantCommandIds.OPEN_MY_NEW, label: 'Show My New Widget' }, {
            execute: () => this.openView({ activate: true, reveal: true }),
        });
    }
    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(AQP_QUANT_VIEWS, {
            commandId: AqpQuantCommandIds.OPEN_MY_NEW,
            label: MyNewWidget.LABEL,
            order: '4',
        });
    }
}
```

## Step 5 — Wire the DI bindings

In `src/browser/aqp-quant-frontend-module.ts`:

```typescript
bind(MyNewWidget).toSelf();
bind(WidgetFactory).toDynamicValue(ctx => ({
    id: MyNewWidget.ID,
    createWidget: () => ctx.container.get(MyNewWidget),
})).inSingletonScope();

bind(MyNewViewContribution).toSelf().inSingletonScope();
bind(CommandContribution).toService(MyNewViewContribution);
bind(MenuContribution).toService(MyNewViewContribution);
bind(FrontendApplicationContribution).toService(MyNewViewContribution);
```

## Step 6 — REST integration

Add REST calls through `AqpApiService` (or extend `AqpRuntimeClient` if
the call fits the spec-runtime pattern). NEVER `fetch` directly.

For streaming, inject `AqpWsClient` and call `subscribe(taskId)`. The
returned subscription emits `AqpProgressFrame` events that honour
AQP rule 4 verbatim.

## Step 7 — Update docs

1. Update `aqp_ide/docs/quant-widgets.md` with the new widget row.
2. Update `aqp_ide/docs/extensions.md` with the new file paths.
3. Update the extension's `README.md`.
4. If the widget surfaces a new AQP capability that monorepo readers
   should know about, cross-link from `aqp_docs/docs/concepts/infrastructure/aqp-ide.md`.

## Step 8 — Validate

```bash
yarn build:extensions
yarn build:applications:dev
aqp-cli ide doctor
aqp-cli ide start --open
# In Theia: View → AQP → Show My New Widget → confirm:
# - Auth0 gate works (sign in first)
# - Loads data without console errors
# - Tenancy QuickPick changes are reflected
# - (if streaming) frames render via canonical shape
```

## Step 9 — Reflect into aqp_index

Per the always-on `aqp-index-reflect.mdc` rule, refresh `aqp_index/`
via the `aqp-index-curator` subagent OR open a debt note at
`.cursor/plans/aqp-index-debt-<slug>.md`.

## Don't list

- Don't `fetch()` directly — use `AqpApiService`.
- Don't `new WebSocket(...)` directly — use `AqpWsClient`.
- Don't render outside `Auth0Bridge` — subclass `AqpWidgetBase` which
  wraps it for you.
- Don't add CSS outside the `.aqp-widget` namespace.
- Don't hard-code the AQP API base URL — read it from
  `AqpConfigService`.
- Don't bypass the canonical progress frame for WebSocket streams.
- Don't skip the doc updates — `aqp-ide-curator` enforces them.
