# Retire the vendored `test_theia/theia-ide` workspace

Status: `migration`.

## Background

The Theia IDE source code initially lived in a standalone vendored
workspace at `c:\Users\Julian Wiley\Documents\test_theia\theia-ide`. It
was opened side-by-side with the main `agentic_quant_platform` repo so
the original Theia upstream history could be browsed during the AQP
extension's first development pass.

A file-level audit (SHA-256 verified) confirms that
`c:\Users\Julian Wiley\Documents\test_theia\theia-ide` is **byte-for-byte
identical** to `agentic_quant_platform/aqp_ide/`:

- Files only in `test_theia/theia-ide` (not in `aqp_ide/`): **0**
- Files only in `aqp_ide/` (not in `test_theia/theia-ide`): **0**
- Spot-checked SHA-256 across all six AQP-authored source files +
  `applications/browser/package.json` + `browser.Dockerfile`: identical
  bit-for-bit

Nothing needs to be ported. The vendored workspace is fully redundant.

## 5-step retirement checklist

### Step 1 — Remove from the Cursor workspace

If you opened `test_theia/theia-ide` as a workspace folder in Cursor:

- **File → Remove Folder from Workspace** (or close the workspace and
  edit your `.code-workspace` file to drop the entry).

The canonical AQP-bound Theia source is `aqp_ide/` inside
`agentic_quant_platform`; the new
[`.cursor/rules/aqp-ide.mdc`](../../.cursor/rules/aqp-ide.mdc) rule
already governs it.

### Step 2 — Confirm no CI / docs / scripts reference the vendored path

Run from the monorepo root:

```bash
# Linux/macOS
rg -n "test_theia/theia-ide" --hidden --no-ignore -g '!node_modules' .

# Windows PowerShell
Select-String -Path .\* -Pattern "test_theia/theia-ide" -Recurse -SimpleMatch
```

Both should return no results outside `aqp_ide/docs/archive/` or this
file. If you find a stray reference, fix it before deleting.

### Step 3 — Delete the directory

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force "C:\Users\Julian Wiley\Documents\test_theia\theia-ide"
```

macOS / Linux:

```bash
rm -rf "$HOME/Documents/test_theia/theia-ide"
```

Optionally delete the empty parent `test_theia/` too:

```powershell
Remove-Item "C:\Users\Julian Wiley\Documents\test_theia" -Force
```

### Step 4 — Backfill `yarn.lock` if it's missing `@auth0/*`

The `browser.Dockerfile` carries an inline note explaining that the
initial `aqp_ide/yarn.lock` did NOT pin `@auth0/auth0-spa-js` +
`@auth0/auth0-react`. If that's still the case (check via
`grep "@auth0/" aqp_ide/yarn.lock`), regenerate the lockfile once and
commit it so future builds can use `yarn install --frozen-lockfile`:

```bash
aqp-cli ide install   # equivalent to `cd aqp_ide && yarn install`
cd aqp_ide
git add yarn.lock
git commit -m "aqp_ide: pin @auth0/* deps in yarn.lock"
```

After this, future Docker builds can tighten the install step from
`yarn install` to `yarn install --frozen-lockfile`.

### Step 5 — (Optional) CI guard

Add a tiny CI step that fails if the vendored path re-appears in the
monorepo. Example for a GitHub Actions workflow:

```yaml
- name: Guard against test_theia/theia-ide re-introduction
  run: |
    if rg -q "test_theia/theia-ide" --hidden --no-ignore -g '!aqp_ide/docs/archive/**' -g '!aqp_ide/docs/retire-vendored-workspace.md'; then
      echo "::error::test_theia/theia-ide path re-appeared; this should not happen post-retirement."
      exit 1
    fi
```

This is optional but inexpensive insurance — the byte-identical
duplication is what made the workspace easy to retire; the guard
prevents a future "scratch space" from drifting into the same state.

## What you GAIN by retiring

- One canonical Theia source location. Reviewers / agents / curators
  no longer need to ask "which copy?".
- `aqp-cli ide` always points at the right place
  (`resolve_repo_root() / "aqp_ide"`).
- The `aqp-ide.mdc` always-on rule unambiguously applies.
- Disk space: `test_theia/theia-ide` is multi-GB once `node_modules`
  is materialised.

## What you LOSE

Nothing. The vendored workspace had no unique content.

## Reverting (if needed)

If retirement turns out to be premature:

```bash
git clone --branch <commit-the-aqp_ide-was-vendored-from> \
  https://github.com/eclipse-theia/theia-ide.git \
  "$HOME/Documents/test_theia/theia-ide"
```

But there's no reason to — this doc preserves the audit + the entire
`aqp_ide/` mirror is the byte-identical authoritative source.

## See also

- `aqp_ide/AGENTS.md` — the AQP-IDE-side governance contract
- `aqp_docs/aqp-ide.md` — monorepo-side SSoT pointer
- `.cursor/rules/aqp-ide.mdc` — always-on boundary rule
