# Widget template (ReactWidget + Factory + View Contribution)

Three files plus a module binding ship a custom view into Theia's workbench.

## `src/browser/my-widget.tsx`

```typescript
import { ReactWidget } from '@theia/core/lib/browser';
import { MessageService } from '@theia/core';
import { inject, injectable, postConstruct } from '@theia/core/shared/inversify';
import * as React from '@theia/core/shared/react';
import { AlertMessage } from '@theia/core/lib/browser/widgets/alert-message';

@injectable()
export class MyWidget extends ReactWidget {
    static readonly ID = 'my-widget';
    static readonly LABEL = 'My Widget';

    @inject(MessageService)
    protected readonly messageService!: MessageService;

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
                <AlertMessage type="INFO" header="My Widget loaded." />
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

## `src/browser/my-widget-contribution.ts`

```typescript
import {
    AbstractViewContribution,
    CommonMenus
} from '@theia/core/lib/browser';
import {
    Command,
    CommandRegistry,
    MenuModelRegistry
} from '@theia/core';
import { injectable } from '@theia/core/shared/inversify';
import { MyWidget } from './my-widget';

export const MyWidgetCommand: Command = {
    id: 'my-widget:toggle',
    label: 'Toggle My Widget'
};

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
            execute: () => this.openView({ activate: false, reveal: true })
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

## `src/browser/my-widget-frontend-module.ts`

```typescript
import { ContainerModule } from '@theia/core/shared/inversify';
import { WidgetFactory } from '@theia/core/lib/browser';
import { CommandContribution, MenuContribution } from '@theia/core';
import { MyWidget } from './my-widget';
import { MyWidgetContribution } from './my-widget-contribution';

export default new ContainerModule(bind => {
    bind(MyWidget).toSelf();
    bind(WidgetFactory).toDynamicValue(ctx => ({
        id: MyWidget.ID,
        createWidget: () => ctx.container.get<MyWidget>(MyWidget)
    })).inSingletonScope();

    bind(MyWidgetContribution).toSelf().inSingletonScope();
    bind(CommandContribution).toService(MyWidgetContribution);
    bind(MenuContribution).toService(MyWidgetContribution);
});
```

## Lifecycle hooks worth knowing

Override these methods on `MyWidget` if needed:

- `onActivateRequest(msg)` — focus the right element when the view receives focus.
- `onUpdateRequest(msg)` — runs on `this.update()`; `render()` is called from here.
- `onResize(msg)` — react to size changes (canvas, virtualized lists).
- `onAfterAttach(msg)` / `onAfterDetach(msg)` — wire up and tear down event listeners.

## Multi-instance widgets (e.g. one per URI)

Replace `getOrCreate` arguments with an options object and accept them in the factory:

```typescript
bind(WidgetFactory).toDynamicValue(ctx => ({
    id: MyWidget.ID,
    createWidget: async (options: { uri: string }) => {
        const widget = ctx.container.get<MyWidget>(MyWidget);
        widget.id = `${MyWidget.ID}:${options.uri}`;
        widget.title.label = `My Widget — ${options.uri}`;
        return widget;
    }
}));
```

Open with `widgetManager.getOrCreateWidget(MyWidget.ID, { uri })`.

## Tips

- Always `bind(MyWidget).toSelf()` in addition to the factory binding, otherwise `ctx.container.get(MyWidget)` cannot construct.
- Use `@theia/core/shared/react` instead of `react` to avoid duplicate React copies.
- Call `this.update()` after data changes; React alone will not re-render an attached widget.
- For tree-shaped data, prefer `TreeWidget` and an associated `TreeModel`.
