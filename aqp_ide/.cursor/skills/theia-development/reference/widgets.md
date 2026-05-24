# Widgets

A widget is the unit of UI in the Theia workbench. Anything you see that can be docked, dragged, resized, or closed — file explorer, editor, problems view, terminal — is a widget. Theia provides base classes for the common cases so you only write the custom rendering and behaviour.

## Base classes

Pick the closest base class:

| Base class | Use for |
|------------|---------|
| `BaseWidget` | Bare-bones widget. You manage DOM directly via `node`. |
| `ReactWidget` | Render React in the `render()` method. Most custom views start here. |
| `TreeWidget` | Tree view with selection, expansion, focus handling. |
| `MessageWidget`, `EditorWidget`, etc. | Specialized widgets that ship with Theia. |

Browse the `BaseWidget` subclass hierarchy in `@theia/core/lib/browser` to discover others (file dialog, output, debug toolbar, ...).

## Anatomy of a custom widget

Three pieces wire a widget into Theia:

1. The widget class — UI and behaviour.
2. A `WidgetFactory` binding — tells the `WidgetManager` how to create the widget.
3. An `AbstractViewContribution` — registers the command and menu entry that opens the widget.

### 1. The widget class

```typescript
import { ReactWidget } from '@theia/core/lib/browser';
import { MessageService } from '@theia/core';
import { injectable, inject, postConstruct } from '@theia/core/shared/inversify';
import * as React from '@theia/core/shared/react';
import { AlertMessage } from '@theia/core/lib/browser/widgets/alert-message';

@injectable()
export class MyWidget extends ReactWidget {
    static readonly ID = 'my:widget';
    static readonly LABEL = 'My Widget';

    @inject(MessageService)
    protected readonly messageService: MessageService;

    @postConstruct()
    protected init(): void {
        this.id = MyWidget.ID;
        this.title.label = MyWidget.LABEL;
        this.title.caption = MyWidget.LABEL;
        this.title.closable = true;
        this.title.iconClass = 'codicon codicon-symbol-class';
        this.update();
    }

    protected render(): React.ReactNode {
        return (
            <div id="widget-container">
                <AlertMessage type="INFO" header="This widget calls MessageService." />
                <button
                    className="theia-button secondary"
                    onClick={() => this.displayMessage()}
                >
                    Display Message
                </button>
            </div>
        );
    }

    protected displayMessage(): void {
        this.messageService.info('Hello from MyWidget!');
    }
}
```

Lifecycle hooks worth overriding (from Phosphor's `Widget`):

- `onActivateRequest` — focus the widget's primary element.
- `onUpdateRequest` — re-render; usually called by `this.update()`.
- `onResize` — react to size changes (e.g. resize a canvas).
- `onAfterAttach` / `onAfterDetach` — set up and tear down event listeners.

### 2. Widget factory

The `WidgetManager` creates and tracks widgets by ID. Register a factory that knows how to produce yours:

```typescript
import { WidgetFactory } from '@theia/core/lib/browser';

export default new ContainerModule(bind => {
    bind(MyWidget).toSelf();
    bind(WidgetFactory).toDynamicValue(ctx => ({
        id: MyWidget.ID,
        createWidget: () => ctx.container.get<MyWidget>(MyWidget)
    })).inSingletonScope();
});
```

`createWidget` can accept arguments if you call `widgetManager.getOrCreateWidget(MyWidget.ID, { ... })`. Use that for editors that need a URI or views that need configuration.

### 3. View contribution

`AbstractViewContribution` ties the widget to a command and menu entry, handles default placement, and persists open state across sessions.

```typescript
import { AbstractViewContribution, CommonMenus } from '@theia/core/lib/browser';
import { Command, CommandRegistry, MenuModelRegistry } from '@theia/core';

export const MyWidgetCommand: Command = { id: 'my-widget:toggle', label: 'Toggle My Widget' };

@injectable()
export class MyWidgetContribution extends AbstractViewContribution<MyWidget> {
    constructor() {
        super({
            widgetId: MyWidget.ID,
            widgetName: MyWidget.LABEL,
            defaultWidgetOptions: { area: 'left' },
            toggleCommandId: MyWidgetCommand.id
        });
    }

    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(MyWidgetCommand, {
            execute: () => super.openView({ activate: false, reveal: true })
        });
    }

    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(CommonMenus.VIEW_VIEWS, {
            commandId: MyWidgetCommand.id,
            label: MyWidget.LABEL
        });
    }
}
```

Bind it as both `CommandContribution` and `MenuContribution`:

```typescript
bind(MyWidgetContribution).toSelf().inSingletonScope();
bind(CommandContribution).toService(MyWidgetContribution);
bind(MenuContribution).toService(MyWidgetContribution);
```

`AbstractViewContribution` already implements both interfaces, so a single instance is bound through `toService`.

## Widget areas

`defaultWidgetOptions.area` controls where the widget opens by default:

- `'left'`, `'right'` — side panels
- `'bottom'` — bottom panel (problems, output)
- `'main'` — main editor area
- `'top'` — top toolbar area

`mode` can be `'tab-after'`, `'tab-before'`, `'split-right'`, `'split-bottom'`, etc., for relative placement. See `ApplicationShell.WidgetOptions` for the full list.

## Opening widgets programmatically

```typescript
@inject(WidgetManager) protected readonly widgetManager: WidgetManager;
@inject(ApplicationShell) protected readonly shell: ApplicationShell;

async openMyWidget(): Promise<void> {
    const widget = await this.widgetManager.getOrCreateWidget(MyWidget.ID);
    this.shell.addWidget(widget, { area: 'left' });
    this.shell.activateWidget(widget.id);
}
```

`getOrCreateWidget` returns an existing instance if one was already created, so widgets are typically single-instance per ID. Pass an options object as the second argument to support multi-instance widgets (e.g. opening a custom editor per URI).

## React utilities

`@theia/core/shared/react` re-exports React so all extensions agree on the same instance. Use it instead of importing `react` directly to avoid duplicate React copies and broken hooks.

For state that lives outside the React tree (Theia services, RPC subscriptions), drive re-renders by calling `this.update()` from the widget after data changes. Inside JSX you can use `React.useState`, `React.useEffect`, etc., for view-local state.

## Tree widgets

`TreeWidget` is heavier but saves significant work for tree-shaped data. Provide:

- A `TreeModel` (often a `TreeModelImpl` you subclass).
- A `TreeProps` for selection / expansion behaviour.
- A `TreeNode` type for your domain.

The widget handles keyboard navigation, drag-and-drop hooks, focus rings, and styling. See `@theia/core/lib/browser/tree` for the canonical examples.

## Persisting widget state

Override `storeState` and `restoreState` to save and rehydrate widget-specific state across reloads. The framework calls them automatically as part of layout serialization. Keep stored state JSON-serializable.

```typescript
override storeState(): object {
    return { selectedTab: this.selectedTab };
}
override restoreState(oldState: object): void {
    if (oldState && typeof (oldState as any).selectedTab === 'string') {
        this.selectedTab = (oldState as any).selectedTab;
    }
}
```

## Common pitfalls

- Forgetting `this.update()` after state changes — the widget won't re-render.
- Binding `MyWidget` only as `WidgetFactory` and not also as `bind(MyWidget).toSelf()` — the factory's `ctx.container.get(MyWidget)` will fail.
- Holding DOM references in non-React widgets across `detach`/`attach` cycles — the node tree is recreated.
- Importing `react` directly instead of `@theia/core/shared/react` — leads to two React copies and hook breakage.
- Using a non-unique widget `id` — Theia tracks widgets by ID and will collide.

See `templates/widget-contribution.tsx.md` for a paste-ready scaffold.
