# aqp_index debt — aqp_ui marketing expansion

Date: 2026-05-25
Author: aqp-ui content & polish plan

## What changed

The `aqp_ui/` package received a major content + visual upgrade. The public
surface area grew with new routes; the design system gained `framer-motion`
and `recharts`; a new `src/components/marketing/` primitives library was
introduced.

Because this touches the public surface of an `aqp_*` package, the
[aqp-index-reflect](../rules/aqp-index-reflect.mdc) always-on rule applies.
This note is the cheap-compliance path until the next
[aqp-index-curator](../agents/aqp-index-curator.md) pass.

## Surfaces the curator needs to refresh

### Route table (new public pages)

The `aqp_ui/src/app/(marketing)/` route tree now includes:

- `/product/agentops` — product page
- `/product/reinforcement-learning` — product page
- `/product/data-platform` — product page
- `/product/backtesting` — product page
- `/cloud` — cloud PaaS product page
- `/self-hosted` — self-hosted product page
- `/learn` — learn hub index
- `/learn/agentops-in-finance`
- `/learn/multi-agent-patterns`
- `/learn/hash-locked-specs`
- `/learn/reinforcement-learning-in-finance`
- `/learn/finrl-x-portfolio-pipeline`
- `/learn/medallion-data-platform`

Existing routes that were polished but kept at the same URL:
`/`, `/about`, `/pricing`, `/blog`, `/(marketing)/layout.tsx`.

### Component surface

A new `aqp_ui/src/components/marketing/` directory:

```
marketing/
├── MarketingShell.tsx       — page wrapper + Container helper
├── Hero.tsx                  — animated hero
├── FeatureCard.tsx           — glass-morphism card
├── FeatureGrid.tsx           — stagger reveal grid
├── FeatureBreakdown.tsx      — alternating row layout
├── StatStrip.tsx             — animated count-up row
├── CodeBlock.tsx             — code with chrome + copy
├── ComparisonTable.tsx       — cloud vs self-hosted table
├── FaqAccordion.tsx          — collapsible FAQ
├── SectionHeader.tsx         — eyebrow + title + subtitle
├── CallToActionBlock.tsx     — gradient CTA card
├── LogoCloud.tsx             — text-chip integration strip
├── MotionInView.tsx          — framer-motion in-view helper
├── MetricSparkline.tsx       — recharts mini area chart
├── ProductNav.tsx            — sticky anchor nav
├── LearnArticleLayout.tsx    — long-form article shell
├── MarketingNav.tsx          — main site nav with Products dropdown
└── illustrations/
    ├── AgentFlowDiagram.tsx
    ├── RLLoopDiagram.tsx
    ├── MedallionLayers.tsx
    ├── MultiTenantIllustration.tsx
    └── WorkflowOrchestrationDiagram.tsx
```

### Token + style surface

`aqp_ui/src/app/globals.css` gained:

- `--gradient-hero`, `--gradient-hero-soft`, `--gradient-mesh`,
  `--gradient-text-primary`, `--gradient-text-accent`
- Glass-morphism: `--glass-bg`, `--glass-bg-strong`, `--glass-border`,
  `--glass-border-strong`, `--glass-blur`
- Shadows: `--shadow-elevated`, `--shadow-card`, `--shadow-glow-primary`,
  `--shadow-glow-secondary`, `--shadow-glow-success`
- Accents: `--accent-secondary` (purple), `--accent-tertiary` (green)
- Utility classes: `.heading-gradient`, `.heading-shimmer`, `.glass-card`,
  `.glass-card-strong`, `.mesh-bg`, `.gradient-border`, `.container-marketing`,
  `.prose-article`
- Keyframes: `shimmer`, `gradient-shift`, `float-slow`, `pulse-glow`,
  `flow-line`, `spin-slow` + matching `.animate-*` classes
- `prefers-reduced-motion` honour
- Light-mode glass + gradient overrides under `:root.light`

### Dependency surface

`aqp_ui/package.json` added two runtime deps:

- `framer-motion ^11.11.0`
- `recharts ^2.15.0`

No new devDependencies. No new global / module aliases. No new env vars.

## Files for the curator to update

When the next `aqp-index-curator` pass runs, the following files under
`aqp_index/` likely need refreshing:

- `aqp_index/project-index.md` — add the new route tree + marketing
  components to the `aqp_ui` section.
- `aqp_index/code-indices/aqp_ui.md` — refresh the surface inventory.
- `aqp_index/architecture/frontend-pointers.md` (if exists) — note the new
  marketing primitives library + the framer-motion / recharts additions.
- `aqp_index/skills/frontend-skill.md` (if exists) — note the new component
  conventions: `.glass-card`, `.heading-gradient`, `MotionInView` wrapper.

## Hard rules this change respects

- AGENTS rule 22 (no `aqp.*` imports in `aqp_ui`) — verified: no new
  imports cross the boundary.
- AGENTS rule 4 (canonical progress frame) — no WS frame shape touched.
- AGENTS rule 27 (IdentityProvider chain) — no auth code touched.
- AGENTS rule 51 (TenancyStrategy) — no tenancy code touched.
- AGENTS rule 52 (step-up MFA) — no step-up gates touched.
- CVE-2025-29927 pin — `next` stays on `14.2.30`; no middleware changes.

## Hard rules this change does NOT trigger refresh of

- No new `aqp_*` package added.
- No `aqp.*` ORM model change.
- No new MCP tool / DataMCP class.
- No migration added under `alembic/versions/`.
- No public Settings field added.
- No public agent / bot / RL / workflow spec field added.

The refresh is intentionally `aqp_ui`-scoped.
