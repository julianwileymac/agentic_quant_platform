"""Reusable Solara components for the AQP UI.

Components are organised into sub-packages so imports stay cheap:

- :mod:`aqp.ui.components.data`    — fetch hooks, metric tiles, entity tables,
  task / live streamers, equity cards.
- :mod:`aqp.ui.components.charts`  — candlestick, heatmap, stats grid.
- :mod:`aqp.ui.components.forms`   — schema-driven form, YAML editor,
  strategy parameter editor.
- :mod:`aqp.ui.components.layout`  — tab / card / split-pane / Dash embed
  primitives used to compose dense pages.

Legacy chat + agent-trace components are re-exported here so existing pages
continue to work unchanged.
"""

from aqp.ui.components.agent_trace import AgentTrace
from aqp.ui.components.chat_message import ChatBubble
from aqp.ui.components.charts.candlestick import (
    Candlestick,
    IndicatorOverlay,
    SUPPORTED_CHART_FEATURES,
    build_security_figure,
)
from aqp.ui.components.charts.heatmap import Heatmap
from aqp.ui.components.charts.stats_grid import StatsGrid
from aqp.ui.components.data.entity_table import EntityTable
from aqp.ui.components.data.equity_card import EquityCard
from aqp.ui.components.data.metric_tile import MetricTile, TileTrend
from aqp.ui.components.data.task_streamer import LiveStreamer, TaskStreamer, WSStatus
from aqp.ui.components.data.use_api import use_api, use_api_action
from aqp.ui.components.forms.form_builder import FieldSpec, FormBuilder
from aqp.ui.components.forms.parameter_editor import (
    ModelCatalog,
    ParameterEditor,
)
from aqp.ui.components.forms.yaml_editor import YamlEditor
from aqp.ui.components.layout.card_grid import CardGrid
from aqp.ui.components.layout.dash_embed import DashEmbed
from aqp.ui.components.layout.split_pane import SplitPane
from aqp.ui.components.layout.tab_panel import TabPanel, TabSpec

__all__ = [
    "AgentTrace",
    "Candlestick",
    "CardGrid",
    "ChatBubble",
    "DashEmbed",
    "EntityTable",
    "EquityCard",
    "FieldSpec",
    "FormBuilder",
    "Heatmap",
    "IndicatorOverlay",
    "LiveStreamer",
    "MetricTile",
    "ModelCatalog",
    "ParameterEditor",
    "SplitPane",
    "SUPPORTED_CHART_FEATURES",
    "StatsGrid",
    "TabPanel",
    "TabSpec",
    "TaskStreamer",
    "TileTrend",
    "WSStatus",
    "YamlEditor",
    "build_security_figure",
    "use_api",
    "use_api_action",
]
