# Extension `package.json` template

A minimal `package.json` for a Theia extension. The `keywords` array and the `theiaExtensions` array are mandatory — they are how Theia discovers the extension's DI modules at startup.

## Minimal frontend-only extension

```json
{
    "name": "my-extension",
    "version": "0.0.0",
    "description": "Adds a custom command and view to the Theia workbench.",
    "license": "EPL-2.0 OR GPL-2.0-only WITH Classpath-exception-2.0",
    "private": true,
    "keywords": ["theia-extension"],
    "files": ["lib", "src"],
    "dependencies": {
        "@theia/core": "latest"
    },
    "devDependencies": {
        "rimraf": "latest",
        "typescript": "~5.4.5"
    },
    "scripts": {
        "prepare": "yarn run clean && yarn run build",
        "clean":   "rimraf lib",
        "build":   "tsc",
        "watch":   "tsc -w"
    },
    "theiaExtensions": [
        {
            "frontend": "lib/browser/my-extension-frontend-module"
        }
    ]
}
```

## Frontend + backend

```json
{
    "name": "my-extension",
    "version": "0.0.0",
    "keywords": ["theia-extension"],
    "files": ["lib", "src"],
    "dependencies": {
        "@theia/core": "latest",
        "@theia/filesystem": "latest"
    },
    "devDependencies": {
        "rimraf": "latest",
        "typescript": "~5.4.5"
    },
    "scripts": {
        "prepare": "yarn run clean && yarn run build",
        "clean":   "rimraf lib",
        "build":   "tsc",
        "watch":   "tsc -w"
    },
    "theiaExtensions": [
        {
            "frontend": "lib/browser/my-extension-frontend-module",
            "backend":  "lib/node/my-extension-backend-module"
        }
    ]
}
```

## With a Theia AI agent

```json
{
    "name": "my-ai-extension",
    "version": "0.0.0",
    "keywords": ["theia-extension"],
    "files": ["lib", "src"],
    "dependencies": {
        "@theia/core": "latest",
        "@theia/ai-core": "latest",
        "@theia/ai-chat": "latest"
    },
    "devDependencies": {
        "rimraf": "latest",
        "typescript": "~5.4.5"
    },
    "scripts": {
        "prepare": "yarn run clean && yarn run build",
        "clean":   "rimraf lib",
        "build":   "tsc",
        "watch":   "tsc -w"
    },
    "theiaExtensions": [
        {
            "frontend": "lib/browser/my-ai-agent-frontend-module"
        }
    ]
}
```

## `tsconfig.json` companion

```json
{
    "compilerOptions": {
        "module": "commonjs",
        "target": "ES2020",
        "lib": ["ES2020", "DOM"],
        "jsx": "react",
        "experimentalDecorators": true,
        "emitDecoratorMetadata": true,
        "moduleResolution": "node",
        "sourceMap": true,
        "declaration": true,
        "rootDir": "src",
        "outDir": "lib",
        "esModuleInterop": true,
        "strict": true,
        "skipLibCheck": true
    },
    "include": ["src"]
}
```

## Consuming application `package.json` (excerpt)

For the `browser-app` (or `electron-app`) to pick up the extension, add it to `dependencies`:

```json
{
    "name": "browser-app",
    "version": "0.0.0",
    "private": true,
    "dependencies": {
        "@theia/core": "latest",
        "@theia/editor": "latest",
        "@theia/filesystem": "latest",
        "@theia/markers": "latest",
        "@theia/messages": "latest",
        "@theia/monaco": "latest",
        "@theia/navigator": "latest",
        "@theia/preferences": "latest",
        "@theia/process": "latest",
        "@theia/terminal": "latest",
        "@theia/workspace": "latest",
        "my-extension": "0.0.0"
    },
    "devDependencies": {
        "@theia/cli": "latest"
    },
    "scripts": {
        "bundle":  "yarn rebuild && theia build --mode development",
        "rebuild": "theia rebuild:browser --cacheRoot ..",
        "start":   "theia start",
        "watch":   "yarn rebuild && theia build --watch --mode development"
    },
    "theia": {
        "target": "browser"
    }
}
```

For the Electron variant change `theia.target` to `electron` and use `theia rebuild:electron` in the `rebuild` script.

## Field cheatsheet

| Field | Purpose |
|-------|---------|
| `keywords: ["theia-extension"]` | Tells Theia (and other tooling) the package is a Theia extension. Without it, `theia rebuild` and the extension installer ignore the package. |
| `theiaExtensions` | Array of `{ frontend?, backend?, electronMain? }` entries pointing at compiled module files (no extension). |
| `files: ["lib", "src"]` | Publishing manifest. Include `lib` so consumers do not need to compile. |
| `scripts.prepare` | Run on `yarn install`; compiles TypeScript into `lib/`. |
| `dependencies.@theia/...` | Pin to the same version as the consuming application; use `latest` only in local dev. |

## Publishing

```bash
yarn build
yarn publish --access public  # or to a private registry
```

The published tarball contains `lib/` (compiled JS + d.ts) and `src/` (optional source). Consumers add it as a regular dependency and the framework loads the modules listed in `theiaExtensions`.
