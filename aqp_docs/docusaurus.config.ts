// docusaurus.config.ts — Agentic Quant Platform documentation site.
//
// Deploy target: Cloudflare Pages at https://docs.aqp.fund.
// See aqp_platform/terraform/modules/cloudflare_pages_docs/ for the
// hosting plumbing and Phase 4 Access policies.
//
// Hard rules respected:
//   - AGENTS rule 26 (CredentialResolver): all secrets resolve at build
//     time from env vars whose values are injected by the Cloudflare
//     Pages build env (sourced from Vault via the cluster's ExternalSecret
//     chain). No literal tokens here.
//   - aqp-management-engine always-on (credential safety): never log
//     full token values from this file or scripts/.

import type { Config } from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';
import { themes as prismThemes } from 'prism-react-renderer';

const SITE_URL = process.env.AQP_DOCS_SITE_URL ?? 'https://docs.aqp.fund';
const BASE_URL = process.env.AQP_DOCS_BASE_URL ?? '/';
const INKEEP_API_KEY = process.env.AQP_DOCS_INKEEP_API_KEY ?? '';
const POSTHOG_KEY = process.env.AQP_DOCS_POSTHOG_KEY ?? '';
const PLAUSIBLE_DOMAIN = process.env.AQP_DOCS_PLAUSIBLE_DOMAIN ?? 'docs.aqp.fund';
const INSTATUS_PAGE_ID = process.env.AQP_DOCS_INSTATUS_PAGE_ID ?? '';
const GITHUB_REPO_URL = 'https://github.com/julianwileymac/agentic_quant_platform';

const config: Config = {
  title: 'Agentic Quant Platform',
  tagline: 'AgenticOps + RL-Ops, end-to-end. Strategy research, backtests, paper, live.',
  favicon: 'img/favicon.ico',

  url: SITE_URL,
  baseUrl: BASE_URL,
  trailingSlash: false,

  organizationName: 'julianwileymac',
  projectName: 'agentic_quant_platform',
  deploymentBranch: 'main',

  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'warn',
  onBrokenAnchors: 'warn',

  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'es'],
    localeConfigs: {
      en: { label: 'English', direction: 'ltr' },
      es: { label: 'Español', direction: 'ltr' },
    },
  },

  markdown: {
    mermaid: true,
    format: 'mdx',
  },

  themes: ['@docusaurus/theme-mermaid'],

  plugins: [
    [
      '@easyops-cn/docusaurus-search-local',
      {
        hashed: true,
        indexBlog: true,
        indexDocs: true,
        indexPages: true,
        docsRouteBasePath: '/',
        highlightSearchTermsOnTargetPage: true,
        explicitSearchResultPath: true,
        searchBarShortcut: true,
        searchBarShortcutHint: true,
      },
    ],
    [
      '@signalwire/docusaurus-plugin-llms-txt',
      {
        siteTitle: 'Agentic Quant Platform',
        siteDescription:
          'AgenticOps + RL-Ops platform: strategy research, backtests, paper, and live trading.',
        depth: 3,
        runOnPostBuild: true,
        includeOrder: [
          'docs/intro/**',
          'docs/concepts/**',
          'docs/how-to/**',
          'docs/tutorials/**',
          'docs/reference/**',
          'docs/architecture/**',
          'docs/release-notes/**',
        ],
        excludeRoutes: ['/keystatic/**', '/internal/**', '/archive/**'],
      },
    ],
  ],

  presets: [
    [
      'classic',
      {
        docs: {
          path: 'docs',
          routeBasePath: '/',
          sidebarPath: './sidebars.ts',
          editUrl: ({ docPath }) =>
            `${GITHUB_REPO_URL}/edit/main/aqp_docs/docs/${docPath}`,
          showLastUpdateTime: true,
          showLastUpdateAuthor: true,
          breadcrumbs: true,
          remarkPlugins: [],
          rehypePlugins: [],
          docItemComponent: '@theme/DocItem',
        },
        blog: {
          path: 'blog',
          routeBasePath: '/blog',
          showReadingTime: true,
          editUrl: ({ blogPath }) =>
            `${GITHUB_REPO_URL}/edit/main/aqp_docs/blog/${blogPath}`,
          feedOptions: {
            type: ['rss', 'atom'],
            xslt: true,
            title: 'AQP changelog',
          },
          blogTitle: 'Release notes',
          blogDescription: 'Customer-facing AQP release notes (auto-emitted from Changesets).',
        },
        theme: {
          customCss: './src/css/custom.css',
        },
        sitemap: {
          changefreq: 'weekly',
          priority: 0.5,
          ignorePatterns: ['/keystatic/**', '/internal/**'],
        },
        pages: {
          path: 'src/pages',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/aqp-social-card.png',

    metadata: [
      { name: 'keywords', content: 'agentic quant, reinforcement learning, FastAPI, FinRL, Qlib, Lean, AQP' },
      { name: 'robots', content: 'index, follow' },
    ],

    colorMode: {
      defaultMode: 'dark',
      disableSwitch: false,
      respectPrefersColorScheme: true,
    },

    navbar: {
      title: 'AQP',
      logo: {
        alt: 'AQP logo',
        src: 'img/logo.svg',
        srcDark: 'img/logo-dark.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'introSidebar',
          position: 'left',
          label: 'Get started',
        },
        {
          type: 'docSidebar',
          sidebarId: 'conceptsSidebar',
          position: 'left',
          label: 'Concepts',
        },
        {
          type: 'docSidebar',
          sidebarId: 'howToSidebar',
          position: 'left',
          label: 'How-to',
        },
        {
          type: 'docSidebar',
          sidebarId: 'tutorialsSidebar',
          position: 'left',
          label: 'Tutorials',
        },
        {
          type: 'docSidebar',
          sidebarId: 'referenceSidebar',
          position: 'left',
          label: 'Reference',
        },
        { to: '/blog', label: 'Release notes', position: 'left' },
        {
          type: 'docsVersionDropdown',
          position: 'right',
        },
        {
          type: 'localeDropdown',
          position: 'right',
        },
        {
          href: 'https://status.aqp.fund',
          label: 'Status',
          position: 'right',
          target: '_blank',
        },
        {
          href: GITHUB_REPO_URL,
          label: 'GitHub',
          position: 'right',
          'aria-label': 'GitHub repository',
        },
      ],
    },

    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            { label: 'Get started', to: '/intro' },
            { label: 'Concepts', to: '/concepts' },
            { label: 'How-to', to: '/how-to' },
            { label: 'Tutorials', to: '/tutorials' },
            { label: 'API reference', to: '/reference/api' },
            { label: 'Python reference', to: '/reference/python' },
          ],
        },
        {
          title: 'Platform',
          items: [
            { label: 'Operator UI', href: 'https://aqp.fund' },
            { label: 'Control plane', href: 'https://manage.aqp.fund' },
            { label: 'Public API', href: 'https://api.aqp.fund' },
            { label: 'Status', href: 'https://status.aqp.fund' },
          ],
        },
        {
          title: 'Community',
          items: [
            { label: 'GitHub', href: GITHUB_REPO_URL },
            { label: 'Issues', href: `${GITHUB_REPO_URL}/issues` },
            { label: 'Release notes', to: '/blog' },
          ],
        },
        {
          title: 'AI agents',
          items: [
            { label: 'llms.txt', href: '/llms.txt' },
            { label: 'llms-full.txt', href: '/llms-full.txt' },
            { label: 'MCP server', href: '/mcp' },
            { label: 'Agent contract', href: `${GITHUB_REPO_URL}/blob/main/AGENTS.md` },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} AQP. Built with Docusaurus.`,
    },

    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: [
        'bash',
        'powershell',
        'python',
        'typescript',
        'tsx',
        'json',
        'yaml',
        'toml',
        'docker',
        'hcl',
        'sql',
        'rust',
      ],
    },

    mermaid: {
      theme: { light: 'neutral', dark: 'dark' },
    },

    announcementBar: {
      id: 'docs-migration-2026-05',
      content:
        '<strong>New docs site:</strong> we have moved to <a href="https://docs.aqp.fund">docs.aqp.fund</a>. The old GitHub-rendered <code>aqp_docs/</code> tree still resolves but is no longer the canonical surface.',
      backgroundColor: '#0b1220',
      textColor: '#ffffff',
      isCloseable: true,
    },

    // The Inkeep "Ask AI" widget is mounted by src/theme/Root.tsx at
    // runtime. Empty key in dev disables the widget; production env
    // is injected by Cloudflare Pages from Vault.
    inkeep: {
      apiKey: INKEEP_API_KEY,
      integrationId: 'aqp-docs',
      organizationId: 'aqp',
      primaryBrandColor: '#0b1220',
    },

    // Analytics — keys are empty in dev; production envs are injected
    // by Cloudflare Pages. Plausible is cookieless; PostHog runs in
    // anonymized mode.
    posthog: {
      apiKey: POSTHOG_KEY,
      appUrl: 'https://eu.posthog.com',
      enableInDevelopment: false,
    },

    plausible: {
      domain: PLAUSIBLE_DOMAIN,
      trackerSrc: 'https://plausible.io/js/script.outbound-links.js',
    },

    instatus: {
      pageId: INSTATUS_PAGE_ID,
      pageUrl: 'https://status.aqp.fund',
      // 60 s cache; banner rendered in src/theme/Layout.tsx.
      cacheTtlSeconds: 60,
    },

    docs: {
      sidebar: {
        hideable: true,
        autoCollapseCategories: true,
      },
    },
  } satisfies Preset.ThemeConfig,

  // Future versioning. Cardinal pick (per the plan): Stripe date-epoch
  // (2026-06-01, ...). Narrative docs stay always-latest; API
  // reference is version-pinned via the docs version system below
  // and via the dual openapi/*.json files.
};

export default config;
