# Preferences template

A complete schema + proxy + binding for a Theia extension's preferences.

## `src/common/my-preferences.ts`

```typescript
import {
    PreferenceContribution,
    PreferenceProxy,
    PreferenceProxyFactory,
    PreferenceSchema,
    PreferenceScope,
    PreferenceService,
    createPreferenceProxy
} from '@theia/core/lib/common/preferences';
import { interfaces } from '@theia/core/shared/inversify';

export const myExtensionPreferenceSchema: PreferenceSchema = {
    properties: {
        'myExtension.enabled': {
            type: 'boolean',
            default: true,
            description: 'Enable MyExtension functionality.',
            scope: PreferenceScope.User
        },
        'myExtension.timeout': {
            type: 'number',
            default: 5000,
            minimum: 100,
            description: 'Operation timeout in milliseconds.',
            scope: PreferenceScope.Workspace
        },
        'myExtension.logLevel': {
            type: 'string',
            enum: ['error', 'warn', 'info', 'debug'],
            default: 'info',
            description: 'Verbosity of MyExtension logs.',
            enumDescriptions: [
                'Errors only',
                'Warnings and errors',
                'Info, warnings and errors',
                'Everything'
            ]
        },
        'myExtension.tabSize': {
            type: 'number',
            default: 4,
            description: 'Tab size used by MyExtension.',
            overridable: true
        }
    }
};

export interface MyExtensionConfiguration {
    'myExtension.enabled': boolean;
    'myExtension.timeout': number;
    'myExtension.logLevel': 'error' | 'warn' | 'info' | 'debug';
    'myExtension.tabSize': number;
}

export const MyExtensionPreferences = Symbol('MyExtensionPreferences');
export type MyExtensionPreferences = PreferenceProxy<MyExtensionConfiguration>;

export const MyExtensionPreferenceContribution = Symbol('MyExtensionPreferenceContribution');

export function bindMyExtensionPreferences(bind: interfaces.Bind): void {
    bind(MyExtensionPreferenceContribution).toConstantValue({
        schema: myExtensionPreferenceSchema
    });
    bind(PreferenceContribution).toService(MyExtensionPreferenceContribution);

    bind(MyExtensionPreferences).toDynamicValue(ctx => {
        const factory = ctx.container.get<PreferenceProxyFactory>(PreferenceProxyFactory);
        return factory(myExtensionPreferenceSchema);
    }).inSingletonScope();
}

export function createMyExtensionPreferences(service: PreferenceService): MyExtensionPreferences {
    return createPreferenceProxy<MyExtensionConfiguration>(service, myExtensionPreferenceSchema);
}
```

## `src/browser/my-extension-frontend-module.ts`

```typescript
import { ContainerModule } from '@theia/core/shared/inversify';
import { bindMyExtensionPreferences } from '../common/my-preferences';

export default new ContainerModule(bind => {
    bindMyExtensionPreferences(bind);
});
```

## `src/node/my-extension-backend-module.ts` (optional)

```typescript
import { ContainerModule } from '@theia/core/shared/inversify';
import { bindMyExtensionPreferences } from '../common/my-preferences';

export default new ContainerModule(bind => {
    bindMyExtensionPreferences(bind);
});
```

The backend only sees Default and User scopes — keep that in mind when the schema is intended for backend consumption.

## Consuming the preferences

### Typed proxy

```typescript
import { inject, injectable, postConstruct } from '@theia/core/shared/inversify';
import { DisposableCollection } from '@theia/core/lib/common/disposable';
import { MyExtensionPreferences } from '../common/my-preferences';

@injectable()
export class MyService {
    @inject(MyExtensionPreferences)
    protected readonly prefs!: MyExtensionPreferences;

    private readonly toDispose = new DisposableCollection();

    @postConstruct()
    protected init(): void {
        this.applyTimeout(this.prefs['myExtension.timeout']);
        this.toDispose.push(
            this.prefs.onPreferenceChanged(e => {
                if (e.preferenceName === 'myExtension.timeout') {
                    this.applyTimeout(this.prefs['myExtension.timeout']);
                }
            })
        );
    }

    private applyTimeout(value: number): void {
        // ...
    }

    dispose(): void {
        this.toDispose.dispose();
    }
}
```

### Direct service

```typescript
@injectable()
export class MyOtherService {
    @inject(PreferenceService)
    protected readonly preferenceService!: PreferenceService;

    getTimeout(): number {
        return this.preferenceService.get('myExtension.timeout', 5000);
    }
}
```

## Settings UI snippet (`settings.json`)

After installing, users can configure preferences:

```jsonc
{
    "myExtension.enabled": true,
    "myExtension.timeout": 10000,
    "myExtension.logLevel": "debug",
    "[typescript]": {
        "myExtension.tabSize": 2
    }
}
```

The schema descriptions drive the settings UI labels and the JSON validation in the editor.
