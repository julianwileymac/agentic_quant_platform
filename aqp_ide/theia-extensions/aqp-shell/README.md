# theia-ide-aqp-shell-ext

AQP IDE shell: white-label theme, contribution filtering, window-title +
about-dialog rebinds. Sibling of `theia-ide-aqp-ext`.

## What this extension does

| Concern | Implementation |
| --- | --- |
| Window title | `AqpWindowTitleService` rebinds `WindowTitleService` to render `AQP IDE — <workspace>` and append the active tenancy from `AqpTenancyStore` when set |
| About dialog | `AqpAboutDialogContribution` overrides the default with an AQP branded About panel (version, build commit, MCP server URLs, cluster id) |
| Contribution filter | `AqpFilterContribution` hides Getting Started walkthroughs, the GitHub auth provider, and a small set of menu actions that are noise in a quant environment |
| Theme | `style/aqp-theme.css` overrides `--theia-*` CSS custom properties to tighten chrome (smaller icons, denser layout) |

## What this extension does NOT do

- Issue any HTTP requests
- Register any widgets
- Call any AQP REST endpoint
- Configure MCP (see `theia-ide-aqp-mcp-bridge-ext`)
- Configure Theia AI agents (see `theia-ide-aqp-research-copilot-ext`)
- Add notebook MIME renderers (see `theia-ide-aqp-notebook-quant-ext`)

## Files

- [src/browser/aqp-shell-frontend-module.ts](src/browser/aqp-shell-frontend-module.ts)
- [src/browser/filters/aqp-filter-contribution.ts](src/browser/filters/aqp-filter-contribution.ts)
- [src/browser/window/aqp-window-title-contribution.ts](src/browser/window/aqp-window-title-contribution.ts)
- [src/browser/about/aqp-about-dialog-contribution.ts](src/browser/about/aqp-about-dialog-contribution.ts)
- [src/browser/style/aqp-theme.css](src/browser/style/aqp-theme.css)

## Build

```bash
# From aqp_ide/
yarn build:extensions
yarn build:applications:dev
```

## See also

- [../../docs/architecture.md](../../docs/architecture.md)
- [../../docs/extensions.md](../../docs/extensions.md)
