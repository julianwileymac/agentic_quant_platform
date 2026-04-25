"""Page-level chrome: grouped sidebar, top bar, breadcrumb, page headers.

These components wrap the per-page content produced by :mod:`aqp.ui.pages`
and give every page the same high-level scaffolding. They are built on top
of :class:`solara.AppLayout` so the integration with Solara's routing
system stays idiomatic.
"""

from aqp.ui.layout.app_shell import NAV_SECTIONS, AppShell, NavSectionSpec
from aqp.ui.layout.page_header import PageHeader
from aqp.ui.layout.section_nav import SectionNav

__all__ = ["AppShell", "NAV_SECTIONS", "NavSectionSpec", "PageHeader", "SectionNav"]
