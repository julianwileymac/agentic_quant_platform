# AGENTS.md

Agent contract for `theia-ide-aqp-shell-ext`.

## Purpose

White-label the Theia shell as **AQP IDE**, remove default contributions that
do not belong in a quant research environment, and propagate the active AQP
tenancy into the browser window title and About dialog.

This extension is **purely cosmetic + filtering**. It must not call AQP HTTP
endpoints (use `theia-ide-aqp-ext`'s `AqpApiService` if you need that), and it
must not register any widgets or commands beyond `aqp.shell.*` namespace.

## Hard boundaries

1. Keep all overrides inside `theia-extensions/aqp-shell/` — never patch
   upstream Theia packages.
2. CSS overrides MUST target `--theia-*` custom properties only; never write
   colours by hex (they would break dark/light theme switching).
3. `FilterContribution` filters MUST be additive (`include`/`exclude`
   patterns); never remove a contribution by overwriting its registration.
4. Cross-extension dependency on `theia-ide-aqp-ext` is allowed and expected
   (we read the tenancy store + auth state from it). Going the other
   direction is not — `theia-ide-aqp-ext` must NOT depend on this extension.
5. No `import` from `agentic_quant_platform` source. Cross HTTP only.

## Validation

```bash
yarn build:extensions
yarn build:applications:dev
```

After build, verify in the running IDE:
- Window title reads `AQP IDE — <tenancy>` once signed in.
- `Help → About` dialog shows the AQP IDE branding block.
- Default `Getting Started` walkthrough is hidden.
- Default Git `Welcome` view is hidden when no repo is open.
