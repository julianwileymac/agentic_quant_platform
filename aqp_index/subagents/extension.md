# Extending the subagent registry

> Last refreshed: 2026-05-23 (seed).

## How to add a new subagent

1. **Author the Cursor subagent file** at
   `.cursor/agents/<slug>.md` with frontmatter:

   ```yaml
   ---
   name: <slug>
   description: <when to use; include "proactively" if appropriate>
   model: <model slug from the supported list>
   ---
   ```

   The body is the system prompt. Read
   [../skills/aqp-index-curator-skill.md](../skills/aqp-index-curator-skill.md)
   for the curator's authoring style as one reference.

2. **Pick a model deliberately.** The available slugs include:

   - `claude-opus-4-7-thinking-max` - heavy reasoning, large context
   - `claude-4.6-opus-high-thinking`
   - `claude-4.6-sonnet-max-thinking`
   - `claude-4-sonnet`
   - `gpt-5.5-high`, `gpt-5.4-medium`
   - `gpt-5.3-codex-xhigh`
   - `gpt-5.2-codex-high-fast`, `gpt-5.2-high-fast`
   - `gpt-5.1-codex-max-high-fast`
   - `composer-2.5-fast`

3. **Mirror the user-facing page** under [subagents/](.) with file name
   `<slug>.md`. The page MUST include: definition link, scope,
   invocation trigger, what it never does, and the procedure pointer.

4. **Open a `.cursor/plans/` note** asking the curator to add the new
   subagent to the registry table in [README.md](README.md).

## How to retire a subagent

1. Move the Cursor file to `.cursor/agents/archive/<slug>.md` with a
   one-line deprecation note at the top.
2. Move the user-facing page to `subagents/archive/<slug>.md`.
3. Open a `.cursor/plans/` note explaining what replaces it.
4. Curator removes the row from the registry on the next pass.

## Curator's role

The curator MAY refresh the registry table in [README.md](README.md) on
every pass. The curator MUST NOT add or retire subagents on its own
initiative - those changes come from an explicit operator decision.
