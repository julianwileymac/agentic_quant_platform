# Preferences

Theia's preference system gives every extension a typed, layered, JSON-Schema-backed configuration surface. The same code works on the frontend and (since 1.65) on the backend, with the caveat that the backend only sees the Default and User scopes.

## Concepts

- **Preference schema** — JSON-Schema describing keys, types, defaults, descriptions, and scope.
- **Preference service** — `PreferenceService`, used to read, write, and observe preferences.
- **Preference proxy** — optional typed wrapper for an interface that matches the schema.
- **Scope** — where a value is stored: Default, User, Workspace, Folder.

Resolution order (most specific wins): Folder → Workspace → User → Default.

## Storage locations

| Scope | Path |
|-------|------|
| User | `$HOME/.theia/settings.json` (Linux/macOS) or `%USERPROFILE%\.theia\settings.json` (Windows). Theia Blueprint uses `.theia-blueprint/` by default. |
| Workspace | `<workspace>/.theia/settings.json` |
| Folder | `<folder>/.theia/settings.json` for multi-root workspaces |
| Default | code-only (your schema's `default` values plus overrides) |

## Contributing a preference

### 1. Define a schema

```typescript
import { PreferenceSchema, PreferenceScope } from '@theia/core/lib/common/preferences';

export const myPreferenceSchema: PreferenceSchema = {
    properties: {
        'myExt.enabled': {
            type: 'boolean',
            default: true,
            description: 'Enable MyExt functionality',
            scope: PreferenceScope.User
        },
        'myExt.timeout': {
            type: 'number',
            default: 5000,
            minimum: 100,
            description: 'Timeout in milliseconds',
            scope: PreferenceScope.Workspace
        },
        'myExt.logLevel': {
            type: 'string',
            enum: ['error', 'warn', 'info', 'debug'],
            default: 'info',
            description: 'Logging level',
            enumDescriptions: ['Errors only', 'Warnings + errors', 'Info + above', 'Everything']
        },
        'myExt.tabSize': {
            type: 'number',
            default: 4,
            overridable: true
        }
    }
};
```

`scope` controls the *most specific* level where users may set a value. `overridable: true` allows language-specific overrides such as `"[typescript].myExt.tabSize"`.

### 2. Optional: TypeScript interface

```typescript
export interface MyConfiguration {
    'myExt.enabled': boolean;
    'myExt.timeout': number;
    'myExt.logLevel': 'error' | 'warn' | 'info' | 'debug';
    'myExt.tabSize': number;
}
```

### 3. Optional: Preference proxy

```typescript
import {
    createPreferenceProxy, PreferenceProxy, PreferenceService, PreferenceProxyFactory
} from '@theia/core/lib/common/preferences';

export const MyPreferences = Symbol('MyPreferences');
export type MyPreferences = PreferenceProxy<MyConfiguration>;

export function createMyPreferences(service: PreferenceService): MyPreferences {
    return createPreferenceProxy<MyConfiguration>(service, myPreferenceSchema);
}
```

### 4. Bind the schema (and proxy)

```typescript
import { interfaces } from '@theia/core/shared/inversify';
import { PreferenceContribution, PreferenceProxyFactory } from '@theia/core/lib/common/preferences';

export const MyPreferenceContribution = Symbol('MyPreferenceContribution');

export function bindMyPreferences(bind: interfaces.Bind): void {
    bind(MyPreferenceContribution).toConstantValue({ schema: myPreferenceSchema });
    bind(PreferenceContribution).toService(MyPreferenceContribution);
    bind(MyPreferences).toDynamicValue(ctx => {
        const factory = ctx.container.get<PreferenceProxyFactory>(PreferenceProxyFactory);
        return factory(myPreferenceSchema);
    }).inSingletonScope();
}
```

## Consuming preferences

### Via `PreferenceService` directly

```typescript
@injectable()
export class MyService {
    @inject(PreferenceService)
    protected readonly preferenceService: PreferenceService;

    private readonly toDispose = new DisposableCollection();

    getTimeout(): number {
        return this.preferenceService.get('myExt.timeout', 5000);
    }

    async setTimeout(value: number): Promise<void> {
        await this.preferenceService.set('myExt.timeout', value, PreferenceScope.User);
    }

    @postConstruct()
    init(): void {
        this.toDispose.push(
            this.preferenceService.onPreferenceChanged(e => {
                if (e.preferenceName === 'myExt.timeout') {
                    console.log('timeout changed to', this.getTimeout());
                }
            })
        );
    }

    dispose(): void { this.toDispose.dispose(); }
}
```

### Via the typed proxy

```typescript
@injectable()
export class MyService {
    @inject(MyPreferences)
    protected readonly prefs: MyPreferences;

    getTimeout(): number { return this.prefs['myExt.timeout']; }

    @postConstruct()
    init(): void {
        this.prefs.onPreferenceChanged(e => {
            if (e.preferenceName === 'myExt.timeout') {
                this.applyTimeout(this.prefs['myExt.timeout']);
            }
        });
    }
}
```

## Inspecting values across scopes

```typescript
const inspection = this.preferenceService.inspect('myExt.timeout');
inspection.defaultValue;        // baked-in default
inspection.globalValue;         // user scope
inspection.workspaceValue;      // workspace scope
inspection.workspaceFolderValue; // folder scope
inspection.value;               // effective value after resolution
```

## Resource-specific access

```typescript
const encoding = this.preferenceService.get('files.encoding', 'utf8', fileUri);
await this.preferenceService.set('files.encoding', 'utf16', PreferenceScope.Folder, folderUri);
```

## Language-specific overrides

Mark a property `overridable: true` in the schema and users can write:

```jsonc
{
  "myExt.tabSize": 4,
  "[typescript]": { "myExt.tabSize": 2 },
  "[python]":     { "myExt.tabSize": 4 }
}
```

## Programmatic overrides

To register defaults dynamically (e.g. per environment), implement `initSchema`:

```typescript
@injectable()
export class MyPreferenceContributionImpl implements PreferenceContribution {
    readonly schema = myPreferenceSchema;

    async initSchema(schemaService: PreferenceSchemaService): Promise<void> {
        schemaService.registerOverride('myExt.logLevel', 'development', 'debug');
        schemaService.registerOverride('editor.tabSize', 'typescript', 2);
    }
}
```

Schema properties must already be present before overrides are registered.

## Backend preferences

Preferences are available on the backend since 1.65, but the backend can only read Default and User scopes. Workspace and Folder scopes are not accessible from backend services.

If a preference is consumed in the backend, set `scope: PreferenceScope.User` so the schema honestly reflects what the backend can see. If the same preference is also used on the frontend (where Workspace makes sense), document the asymmetry.

Bind the schema in both the frontend and backend modules — typically through a shared `common/` helper:

```typescript
// common/my-preferences.ts
export function bindMyPreferences(bind: interfaces.Bind): void {
    bind(MyPreferenceContribution).toConstantValue({ schema: myPreferenceSchema });
    bind(PreferenceContribution).toService(MyPreferenceContribution);
}

// browser/my-frontend-module.ts
export default new ContainerModule(bind => bindMyPreferences(bind));
// node/my-backend-module.ts
export default new ContainerModule(bind => bindMyPreferences(bind));
```

Both processes ultimately read the same `~/.theia/settings.json`; there are no separate per-process stores.

## Migration note (Theia 1.68)

`oldValue` and `newValue` were removed from `PreferenceChange` because they were unreliable (they reflected the changed scope, not the effective value). Always re-read the current value with `preferenceService.get` or the proxy after receiving a change event.

## Best practices

- Prefer keys of the form `<extensionName>.<area>.<setting>`.
- Always supply a `description` (and `enumDescriptions` when applicable) — it shows up in the settings UI.
- Choose the most restrictive scope that still makes sense.
- Listen for changes; do not cache values across long-lived services without an observer.
- Provide sensible defaults so the extension works without any user configuration.
- Document non-obvious preferences in the extension README.
