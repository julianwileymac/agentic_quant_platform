# Command + Menu + Keybinding template

Drop these files into a Theia extension to add a command, a menu entry, and an optional keybinding.

## `src/browser/my-extension-contribution.ts`

```typescript
import {
    Command,
    CommandContribution,
    CommandRegistry,
    MenuContribution,
    MenuModelRegistry,
    MessageService
} from '@theia/core';
import {
    CommonMenus,
    KeybindingContribution,
    KeybindingRegistry
} from '@theia/core/lib/browser';
import { inject, injectable } from '@theia/core/shared/inversify';

export const MyExtensionCommand: Command = {
    id: 'myExtension.sayHello',
    label: 'Say Hello'
};

@injectable()
export class MyExtensionCommandContribution implements CommandContribution {
    constructor(
        @inject(MessageService) private readonly messageService: MessageService
    ) {}

    registerCommands(registry: CommandRegistry): void {
        registry.registerCommand(MyExtensionCommand, {
            execute: () => this.messageService.info('Hello from MyExtension!')
        });
    }
}

@injectable()
export class MyExtensionMenuContribution implements MenuContribution {
    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(CommonMenus.EDIT_FIND, {
            commandId: MyExtensionCommand.id,
            label: MyExtensionCommand.label
        });
    }
}

@injectable()
export class MyExtensionKeybindingContribution implements KeybindingContribution {
    registerKeybindings(keybindings: KeybindingRegistry): void {
        keybindings.registerKeybinding({
            command: MyExtensionCommand.id,
            keybinding: 'ctrlcmd+alt+h',
            when: 'editorTextFocus'
        });
    }
}
```

## `src/browser/my-extension-frontend-module.ts`

```typescript
import { ContainerModule } from '@theia/core/shared/inversify';
import {
    CommandContribution,
    MenuContribution
} from '@theia/core';
import { KeybindingContribution } from '@theia/core/lib/browser';
import {
    MyExtensionCommandContribution,
    MyExtensionMenuContribution,
    MyExtensionKeybindingContribution
} from './my-extension-contribution';

export default new ContainerModule(bind => {
    bind(CommandContribution).to(MyExtensionCommandContribution);
    bind(MenuContribution).to(MyExtensionMenuContribution);
    bind(KeybindingContribution).to(MyExtensionKeybindingContribution);
});
```

## `package.json` snippet

```json
{
  "name": "my-extension",
  "keywords": ["theia-extension"],
  "version": "0.0.0",
  "dependencies": { "@theia/core": "latest" },
  "theiaExtensions": [
    { "frontend": "lib/browser/my-extension-frontend-module" }
  ]
}
```

## Tips

- The `when` clause syntax matches VS Code's: combine with `&&`, use `editorFocus`, `editorTextFocus`, `editorReadonly`, custom keys, etc.
- `ctrlcmd` is Command on macOS and Ctrl elsewhere — prefer it over hard-coded `ctrl`.
- Add `isEnabled` and `isVisible` to the handler if the command should be context-sensitive (hides from the palette and menus when unavailable).
- Find menu paths under `CommonMenus` (`FILE`, `EDIT_FIND`, `VIEW_VIEWS`, `HELP`, ...).
- To open a custom top-level menu, register a `MenuPath` first and add actions inside it.
