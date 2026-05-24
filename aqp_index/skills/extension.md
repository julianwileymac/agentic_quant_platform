# Extending the project skills

> Last refreshed: 2026-05-23 (seed).

## How to add a new project skill

1. **Draft the skill file** under [skills/](.) using the template at
   the top of [README.md](README.md). Frontmatter MUST contain at least
   `name`, `description`, `owner`, `last_verified`.
2. **Add a Cursor-native pointer** at
   `.cursor/skills/<slug>/SKILL.md` if you want the Cursor Agent to
   auto-load the skill on matching tasks. Cursor's skill format
   accepts the same frontmatter; the body is the skill's procedure.
3. **Register it** by opening a [.cursor/plans/](../../.cursor/plans/)
   note. The curator adds the skill to the registry table in
   [README.md](README.md) on the next pass.

## How to extend an existing skill

1. Edit the skill file directly. Bump `last_verified` in the frontmatter
   to today's date.
2. If the procedure now spans new external concepts, add pointers to the
   relevant `aqp_docs/` pages rather than copying prose.
3. Notify the curator via a `.cursor/plans/` note so the registry table
   in [README.md](README.md) reflects the bump.

## How to retire a skill

1. Move the skill file to `skills/archive/<slug>.md` (create the folder
   if needed) and add a one-line deprecation note at the top.
2. Remove the row from the registry table in [README.md](README.md) on
   the next curator pass; replace with an `archived` row carrying the
   archive date.
3. Open a `.cursor/plans/` note explaining what replaces it.

## Curator's role

The curator MAY:

- Edit any skill file's `last_verified` date during a refresh if the
  skill still applies.
- Rewrite a skill's procedure when scanning surfaces it depends on
  reveals drift (e.g., a renamed file path).
- Open `.cursor/plans/` notes asking the skill's `owner` to verify a
  bigger change.

The curator MUST NOT:

- Add a new skill on its own initiative. New skills come from an
  operator's deliberate workflow choice.
- Move a skill to `archive/` without an operator note approving it.
