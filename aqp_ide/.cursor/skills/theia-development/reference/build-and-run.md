# Build and Run

Theia projects are yarn-managed monorepos. The Theia CLI (`theia` from `@theia/cli`) wraps webpack and Electron tooling so most day-to-day work happens through the scripts the generator (or Blueprint) writes for you.

## Prerequisites

From the [Theia developing guide](https://github.com/eclipse-theia/theia/blob/master/doc/Developing.md#prerequisites):

- Node.js 22 or newer for this repository (`package.json` enforces `>=22`).
- Yarn 1.7.x or later in the 1.x line — Theia does not use Yarn 2/Berry.
- Python 3 (for `node-gyp`).
- Native build chain: Xcode CLT on macOS, build-essential + libsecret on Linux, Visual Studio Build Tools (Desktop C++) on Windows.

```bash
npm install -g yo generator-theia-extension
```

## Generated project scripts

A Yeoman-generated `my-theia-app` root `package.json` looks like:

```json
{
  "private": true,
  "engines": { "yarn": ">=1.7.0 <2", "node": ">=18" },
  "workspaces": ["hello-world", "browser-app", "electron-app"],
  "devDependencies": { "lerna": "2.4.0" },
  "scripts": {
    "build:browser":  "yarn --cwd browser-app bundle",
    "build:electron": "yarn --cwd electron-app bundle",
    "prepare":        "lerna run prepare",
    "postinstall":    "theia check:theia-version",
    "start:browser":  "yarn --cwd browser-app start",
    "start:electron": "yarn --cwd electron-app start",
    "watch:browser":  "lerna run --parallel watch --ignore electron-app",
    "watch:electron": "lerna run --parallel watch --ignore browser-app"
  }
}
```

Per-app `package.json` (browser):

```json
{
  "scripts": {
    "bundle":  "yarn rebuild && theia build --mode development",
    "rebuild": "theia rebuild:browser --cacheRoot ..",
    "start":   "theia start",
    "watch":   "yarn rebuild && theia build --watch --mode development"
  },
  "theia": { "target": "browser" }
}
```

For Electron the `target` is `electron` and `rebuild` calls `theia rebuild:electron`.

## Standard workflow (this repository)

```bash
yarn                        # install + patch hooks
yarn build:extensions       # compile extension packages
yarn build:applications:dev # build browser/electron apps in dev mode
yarn browser start          # serve at http://localhost:3000
```

Iteration loop:

```bash
yarn watch           # incremental rebuilds across workspaces
# in a second terminal
yarn browser start
```

Press F1 in the running app to open the command palette and exercise your contributions.

For Electron:

```bash
yarn build:applications
yarn electron package:preview
```

Electron carries native modules (keytar, etc.); `theia rebuild:electron` is what reconciles them with the Electron Node ABI. Always rerun `rebuild` after switching between `browser` and `electron` builds.

## Theia CLI reference

The CLI is invoked through `npx theia ...` or via the per-app scripts. Common commands:

| Command | Purpose |
|---------|---------|
| `theia build` | Webpack bundle the frontend (and backend bootstrap). Add `--mode development` for source maps. |
| `theia build --watch` | Incremental webpack build. |
| `theia rebuild:browser` | Recompile native dependencies for the browser target. |
| `theia rebuild:electron` | Recompile native dependencies for the Electron renderer. |
| `theia start` | Run the application. |
| `theia download:plugins` | Download the VS Code extensions listed in `theiaPlugins`. |
| `theia check:theia-version` | Verify the `@theia/*` versions in the workspace are consistent. |

`--cacheRoot ..` in the `rebuild` script tells Theia to put native module caches at the repo root rather than inside the app, which speeds up CI.

## Lerna

`lerna run <script>` invokes a script across all workspaces that have it. The generator pins lerna at `2.4.0`; later versions also work. Use `lerna run --parallel watch` to launch every extension's TypeScript watcher at once.

## TypeScript / extension compilation

Each extension has its own `tsconfig.json`. The `prepare` script in `package.json` typically runs:

```json
"scripts": {
    "prepare": "yarn run clean && yarn run build",
    "clean":   "rimraf lib",
    "build":   "tsc",
    "watch":   "tsc -w"
}
```

Theia's `theia build` only bundles the application bootstrap; the extensions themselves are plain TypeScript libraries compiled by `tsc`. That's why running `yarn` at the workspace root (which triggers `prepare` in each workspace through `lerna run prepare`) produces the compiled `lib/` output that the app then imports.

## Adding a new extension to the workspace

1. Create a sibling folder, e.g. `my-new-extension/`, with its own `package.json` (`keywords: ["theia-extension"]`, `theiaExtensions` entry).
2. Add the folder name to the root `package.json`'s `workspaces` array.
3. Add the extension as a dependency in `browser-app` and/or `electron-app` `package.json` (version `0.0.0` for local dev).
4. Run `yarn` at the root — lerna links it in.

## Native dependencies behind a proxy

`node-gyp` does not pick up system or npm proxy settings. If a fresh `yarn install` fails inside a corporate proxy with `ECONNRESET` while fetching node headers, pre-download the headers and feed them via:

```bash
npm_config_tarball=/path/to/node-v18.x.x-headers.tar.gz yarn install
```

The Theia docs reproduce the full failure stack so you can recognize it.

## Working with Blueprint

Blueprint's root `package.json` uses workspaces `applications/*` and `theia-extensions/*`. The scripts mirror the generator's but with `electron`/`browser` namespaced commands:

```bash
yarn                       # install
yarn build                 # build everything
yarn electron start        # run unpackaged desktop app
yarn electron package      # build full installer
yarn electron package:preview  # unpackaged tree only
yarn electron deploy       # publish
yarn download:plugins
```

Blueprint also runs the electron rebuild path during packaging
(`yarn electron rebuild` in this repo).

## Performance tips

- Use `--mode development` while iterating; switch to `--mode production` only for release builds and installers.
- Keep the watch task running and reload the browser/Electron window rather than restarting the dev server.
- Avoid `yarn clean` unless something is genuinely stuck — rebuilding native modules is slow.
- When CI runs `yarn` repeatedly, cache `node_modules` and the Electron / node-gyp header downloads.

## Troubleshooting checklist

| Symptom | First thing to try |
|---------|--------------------|
| Cannot find module `@theia/...` after install | Run `yarn` at the root; let lerna link workspaces. |
| Native module ABI mismatch when launching Electron | `yarn --cwd applications/electron rebuild:electron` (or `yarn electron rebuild`). |
| Webpack reports duplicate React | Replace `import React from 'react'` with `import * as React from '@theia/core/shared/react'`. |
| Plugin folder absent at runtime | Re-run `yarn` or `yarn download:plugins`. |
| Theia version mismatch warnings | `yarn theia check:theia-version` and align `@theia/*` versions. |
| Auto-update fails to find `latest.yml` | Confirm `build.publish` configuration and that the file is uploaded next to the installer. |

For productization beyond `yarn browser start` / `yarn electron start`, see [`reference/blueprint-packaging.md`](blueprint-packaging.md).
