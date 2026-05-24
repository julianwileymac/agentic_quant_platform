# Theia Blueprint and Packaging

Theia Blueprint is the reference desktop product the Theia project ships as the "Theia IDE". Adopters use it as a template for building their own branded desktop product with installers, code signing, and auto-update. Packaging uses [electron-builder](https://www.electron.build/).

## Repository layout

Clone `https://github.com/eclipse-theia/theia-blueprint`. The relevant pieces:

```
theia-blueprint/
  applications/
    electron/
      package.json          # Electron application config + theiaPlugins map
      electron-builder.yml  # installer/packaging configuration
      resources/            # icons + branding assets
      scripts/              # signing, after-pack hooks
    browser/
      package.json          # Optional: browser variant of the product
  theia-extensions/
    theia-blueprint-product/  # custom welcome page, about dialog, branding
    theia-ide-launcher-ext/
    theia-ide-product-ext/
    theia-ide-updater-ext/
  package.json              # workspaces: applications/*, theia-extensions/*
```

The root workspaces already include `theia-extensions/*`, so dropping your extension into that folder registers it automatically.

## Adding extensions to Blueprint

Two paths:

### Local (monorepo)

1. Copy your extension into `theia-extensions/<name>/`.
2. Add it to `applications/electron/package.json` (and `applications/browser/package.json` if you ship a browser variant) under `dependencies`:

   ```jsonc
   "dependencies": {
     "theia-ide-launcher-ext": "1.65.100",
     "theia-ide-product-ext": "1.65.100",
     "theia-ide-updater-ext": "1.65.100",
     "<your-extension>": "0.0.0"
   }
   ```

3. Verify `@theia/core` versions match.
4. `yarn && yarn build`.

### Published

1. `yarn publish` the extension to npm (or a private registry).
2. Add it as a regular dependency.

## Branding

### Application name

`applications/electron/package.json`:

```jsonc
"theia": {
  "frontend": {
    "config": {
      "applicationName": "My Product"
    }
  }
}
```

The application name shows in the window title, About dialog, and Welcome view.

### Icons

`applications/electron/resources/`:

| Platform | File |
|----------|------|
| macOS | `icons.icns` |
| Windows | `icon.ico` |
| Linux | `icons/` (multiple PNG sizes) |

Replace these with your own icons. Keep names identical so existing scripts work.

### Welcome page

Customize by binding a `WidgetFactory` for `GettingStartedWidget.ID`. The Blueprint reference extension shows the pattern:

```typescript
bind(MyWelcomeWidget).toSelf();
bind(WidgetFactory).toDynamicValue(ctx => ({
    id: GettingStartedWidget.ID,
    createWidget: () => ctx.container.get<MyWelcomeWidget>(MyWelcomeWidget)
})).inSingletonScope();
```

### About dialog

Extend `AboutDialog` and rebind:

```typescript
isBound(AboutDialog)
    ? rebind(AboutDialog).to(MyAboutDialog).inSingletonScope()
    : bind(AboutDialog).to(MyAboutDialog).inSingletonScope();
```

### Splash screen (Electron, ≥1.49)

In the application `package.json`:

```jsonc
"theia": {
  "frontend": {
    "config": {
      "electron": {
        "splashScreenOptions": {
          "content": "resources/splash.gif",
          "width": 640,
          "height": 480,
          "minDuration": 1500,
          "maxDuration": 8000
        }
      }
    }
  }
}
```

### Show window early

`theia.frontend.config.electron.showWindowEarly` (default `true`) controls whether the main window appears before content is ready. Set to `false` to wait until the workbench has rendered.

### Preferences directory

Blueprint stores user preferences in `.theia-blueprint/` by default. Customize via `theia-blueprint-variables-server.ts`:

```typescript
override get configDirUri(): string {
    return FileUri.create(path.resolve(os.homedir(), '.my-product')).toString();
}
```

## Bundled VS Code extensions

`applications/electron/package.json` defines `theiaPlugins`:

```jsonc
"theiaPlugins": {
  "redhat.vscode-yaml": "https://open-vsx.org/api/redhat/vscode-yaml/1.14.0/file/redhat.vscode-yaml-1.14.0.vsix"
}
```

Keys are folder names (uniqueness required); values are URLs. Plugins download on `yarn install`, `yarn prepare`, or `yarn download:plugins`. Remove an entry and delete `applications/electron/plugins/<key>/` to fully drop a plugin.

Use [Open VSX](https://open-vsx.org/) by default. Override with `VSX_REGISTRY_URL` for private mirrors.

## electron-builder

The packaging configuration lives in `applications/electron/electron-builder.yml`. Key fields:

```yaml
productName: My Product
appId: com.example.myproduct
artifactName: ${productName}-${version}-${os}-${arch}.${ext}

mac:
  category: public.app-category.developer-tools
  target:
    - dmg
    - zip

win:
  target:
    - nsis
    - portable

linux:
  category: Development
  target:
    - AppImage
    - deb

nsis:
  oneClick: false
  perMachine: false
  allowToChangeInstallationDirectory: true
  installerIcon: resources/installer.ico
  uninstallerIcon: resources/installer.ico
  installerSidebar: resources/installerSidebar.bmp
  license: resources/license.txt
```

Full documentation: <https://www.electron.build/configuration> and the per-target pages (`nsis`, `dmg`, `appimage`, etc.).

### Packaging commands

Run from the repo root:

```bash
yarn                                # install + native rebuild
yarn electron package               # build full installer for current OS
yarn electron package:preview       # unpackaged tree only (faster iteration)
yarn electron deploy                # build + publish (per publish config)
```

You can only package for the OS you are running on, with the exception of cross-builds explicitly supported by electron-builder. See <https://www.electron.build/multi-platform-build>.

## Code signing

### macOS

Set `CSC_LINK` and `CSC_KEY_PASSWORD` environment variables to point at your Developer ID Application certificate. electron-builder runs `codesign` and (optionally) `xcrun notarytool` automatically when notarization config is supplied.

### Windows

For NSIS installers, configure `win.certificateFile` + `win.certificatePassword` (or environment variables) for traditional signing, or use Azure Trusted Signing with `win.azureSignOptions`. EV certificates require `WIN_CSC_LINK`.

### Linux

Linux targets are not typically signed at the package level. AppImage signing uses the `linux.signtoolOptions` block if needed.

### Custom hooks

Blueprint's `applications/electron/scripts/after-pack.js` is the entry point for Eclipse Foundation signing infrastructure. Replace it with your own `afterPack` hook (declared as `afterPack` in `electron-builder.yml`) to integrate your signing workflow. The hook receives the unpacked app directory and is the natural place to invoke `codesign`, `signtool`, or notarization tooling.

## Auto-update

Blueprint uses [electron-updater](https://www.electron.build/auto-update). Configure publish targets in `applications/electron/package.json` under `build.publish` or in `electron-builder.yml` under `publish`. Common targets:

- `generic` — point at any HTTPS server. The first publish entry is used by the updater for lookup.
- `github` — GitHub Releases.
- `s3`, `bintray`, `spaces`, ... — see <https://www.electron.build/configuration/publish>.

The auto-updater reads `latest.yml` / `latest-mac.yml` / `latest-linux.yml` from the configured server and pulls deltas. With `generic`, you publish manually (electron-builder produces the yml files; you upload them).

## Splash and crash reporting

For diagnostics:

- Use Theia's built-in logging (`@theia/core/lib/common/logger`) and surface a log location preference.
- Wire Electron's `crashReporter.start(...)` in the main process if you need crash dumps.

## Releasing

Recommended flow:

1. Bump versions across packages (`lerna version`).
2. CI builds installers for all targets, sets `CSC_*` env vars, and publishes to the configured server.
3. Smoke test the installer on each OS.
4. Tag the release.

Keep `package.json#build.publish` consistent across packages — `electron-builder` reads from the application `package.json`.

## Helpful pointers

- [`theia-blueprint`](https://github.com/eclipse-theia/theia-blueprint) is the canonical reference.
- The community example [`secure-dev-ops/code-realtime`](https://github.com/secure-dev-ops/code-realtime) shows a productized Theia-based tool.
- For per-target options (icons, file associations, MSI args, NSIS scripts, AppImage), keep the [electron-builder docs](https://www.electron.build/configuration) open while editing `electron-builder.yml`.
