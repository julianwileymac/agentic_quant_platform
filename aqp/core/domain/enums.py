"""Expanded enum catalog merging gs-quant, vnpy, and nautilus_trader vocabularies.

These ``StrEnum`` values are the single source of truth for every categorical
choice in the domain model (asset class, instrument class, order type, time in
force, bar aggregation, industry classification scheme, filing type, corporate
action kind, etc.). String-valued enums are used so the same vocabulary can
flow through JSON, YAML recipes, SQLAlchemy columns, and the REST/WebSocket
wire without a conversion layer.

Legacy enums in ``aqp.core.types`` (``Direction``, ``Exchange``, ``Interval``,
``Resolution``, ``TickType``, ``DataNormalizationMode``, the original
``AssetClass``/``SecurityType``/``OrderType``/``OrderSide``/``OrderStatus``)
remain valid and are not duplicated here — this module *adds* richer
vocabularies alongside them.
"""
from __future__ import annotations

from enum import StrEnum


# ---------------------------------------------------------------------------
# Asset taxonomy
# ---------------------------------------------------------------------------


class AssetClass(StrEnum):
    """Top-level taxonomy of tradable-asset families.

    Richer than the legacy :class:`aqp.core.types.AssetClass` — the new
    values cover fixed income, credit, and event/prediction markets in
    addition to the original equity/FX/commodity/crypto/future/option/index
    set.
    """

    EQUITY = "equity"
    FX = "fx"
    RATES = "rates"
    CREDIT = "credit"
    COMMODITY = "commodity"
    CRYPTO = "crypto"
    ALTERNATIVE = "alternative"
    EVENT = "event"
    INDEX = "index"
    MIXED = "mixed"
    CASH = "cash"
    BASE = "base"


class InstrumentClass(StrEnum):
    """Instrument shape orthogonal to :class:`AssetClass`.

    An ``Equity`` AAPL is ``(AssetClass.EQUITY, InstrumentClass.SPOT)``; an
    AAPL 2026-01 200 Call is ``(AssetClass.EQUITY, InstrumentClass.OPTION)``;
    a BTCUSDT perpetual is ``(AssetClass.CRYPTO, InstrumentClass.PERPETUAL)``.
    """

    SPOT = "spot"
    FUTURE = "future"
    FORWARD = "forward"
    OPTION = "option"
    SWAP = "swap"
    CFD = "cfd"
    WARRANT = "warrant"
    CONVERTIBLE = "convertible"
    STRUCTURED_NOTE = "structured_note"
    ETF = "etf"
    INDEX = "index"
    BOND = "bond"
    MONEY_MARKET = "money_market"
    BINARY_OPTION = "binary_option"
    BETTING = "betting"
    PERPETUAL = "perpetual"
    PREDICTION_MARKET = "prediction_market"
    CRYPTO_TOKEN = "crypto_token"
    NFT = "nft"
    SYNTHETIC = "synthetic"
    SPREAD = "spread"


class Product(StrEnum):
    """vnpy-parity product enumeration used by :class:`Instrument` metadata."""

    SPOT = "SPOT"
    FUTURES = "FUTURES"
    OPTION = "OPTION"
    INDEX = "INDEX"
    FOREX = "FOREX"
    ETF = "ETF"
    BOND = "BOND"
    WARRANT = "WARRANT"
    SPREAD = "SPREAD"
    FUND = "FUND"
    CFD = "CFD"
    SWAP = "SWAP"
    CRYPTO = "CRYPTO"
    BETTING = "BETTING"


# ---------------------------------------------------------------------------
# Option/derivatives
# ---------------------------------------------------------------------------


class OptionKind(StrEnum):
    CALL = "call"
    PUT = "put"
    STRADDLE = "straddle"


class OptionStyle(StrEnum):
    EUROPEAN = "european"
    AMERICAN = "american"
    BERMUDAN = "bermudan"
    ASIAN = "asian"


class SettlementType(StrEnum):
    PHYSICAL = "physical"
    CASH = "cash"


class PayReceive(StrEnum):
    """Goldman-style swap leg direction."""

    PAY = "pay"
    RECEIVE = "receive"
    STRADDLE = "straddle"


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


class OrderType(StrEnum):
    """Extended order-type enum covering every shape we support.

    Superset of :class:`aqp.core.types.OrderType` — any legacy value maps 1:1.
    """

    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    MARKET_IF_TOUCHED = "market_if_touched"
    LIMIT_IF_TOUCHED = "limit_if_touched"
    MARKET_TO_LIMIT = "market_to_limit"
    TRAILING_STOP_MARKET = "trailing_stop_market"
    TRAILING_STOP_LIMIT = "trailing_stop_limit"
    MARKET_ON_OPEN = "market_on_open"
    MARKET_ON_CLOSE = "market_on_close"
    FOK = "fok"
    FAK = "fak"
    RFQ = "rfq"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"
    NONE = "none"


class OrderStatus(StrEnum):
    INITIALIZED = "initialized"
    SUBMITTING = "submitting"
    ACCEPTED = "accepted"
    PENDING_UPDATE = "pending_update"
    PENDING_CANCEL = "pending_cancel"
    EMULATED = "emulated"
    RELEASED = "released"
    TRIGGERED = "triggered"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REJECTED = "rejected"
    DENIED = "denied"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    GTD = "gtd"
    AT_THE_OPEN = "at_the_open"
    AT_THE_CLOSE = "at_the_close"


class TriggerType(StrEnum):
    DEFAULT = "default"
    BID_ASK = "bid_ask"
    LAST_PRICE = "last_price"
    DOUBLE_LAST = "double_last"
    DOUBLE_BID_ASK = "double_bid_ask"
    LAST_OR_BID_ASK = "last_or_bid_ask"
    MID_POINT = "mid_point"
    MARK_PRICE = "mark_price"
    INDEX_PRICE = "index_price"


class TrailingOffsetType(StrEnum):
    NO_TRAILING_OFFSET = "no_trailing_offset"
    PRICE = "price"
    BASIS_POINTS = "basis_points"
    TICKS = "ticks"
    PERCENTAGE = "percentage"


class ContingencyType(StrEnum):
    """Relationship between orders in an :class:`OrderList`."""

    NONE = "none"
    OCO = "oco"  # one cancels other
    OUO = "ouo"  # one updates other
    OTO = "oto"  # one triggers other


class LiquiditySide(StrEnum):
    MAKER = "maker"
    TAKER = "taker"
    NONE = "none"


class AggressorSide(StrEnum):
    BUYER = "buyer"
    SELLER = "seller"
    NO_AGGRESSOR = "no_aggressor"


class Offset(StrEnum):
    """vnpy futures-market offset (CTP-style)."""

    NONE = ""
    OPEN = "open"
    CLOSE = "close"
    CLOSE_TODAY = "close_today"
    CLOSE_YESTERDAY = "close_yesterday"


class PositionSide(StrEnum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


# ---------------------------------------------------------------------------
# Market microstructure
# ---------------------------------------------------------------------------


class MarketStatus(StrEnum):
    PRE_OPEN = "pre_open"
    OPEN = "open"
    PAUSE = "pause"
    HALT = "halt"
    CLOSE = "close"
    PRE_CLOSE = "pre_close"


class TradingState(StrEnum):
    ACTIVE = "active"
    HALTED = "halted"
    REDUCING = "reducing"


class BarAggregation(StrEnum):
    """Bar-aggregation basis.

    Covers the common Lopez-de-Prado-style information-bar variants alongside
    the classic time/tick/volume bars.
    """

    TICK = "tick"
    TICK_IMBALANCE = "tick_imbalance"
    TICK_RUNS = "tick_runs"
    VOLUME = "volume"
    VOLUME_IMBALANCE = "volume_imbalance"
    VOLUME_RUNS = "volume_runs"
    VALUE = "value"  # dollar bars
    VALUE_IMBALANCE = "value_imbalance"
    VALUE_RUNS = "value_runs"
    MILLISECOND = "millisecond"
    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class PriceType(StrEnum):
    BID = "bid"
    ASK = "ask"
    MID = "mid"
    LAST = "last"
    MARK = "mark"


class BookType(StrEnum):
    """Depth of an order book."""

    L1_MBP = "l1_mbp"
    L2_MBP = "l2_mbp"
    L3_MBO = "l3_mbo"


class BookAction(StrEnum):
    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"
    CLEAR = "clear"


class InstrumentCloseType(StrEnum):
    END_OF_SESSION = "end_of_session"
    CONTRACT_EXPIRED = "contract_expired"


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


class AccountType(StrEnum):
    CASH = "cash"
    MARGIN = "margin"
    BETTING = "betting"
    CRYPTO = "crypto"


class OmsType(StrEnum):
    NETTING = "netting"
    HEDGING = "hedging"


# ---------------------------------------------------------------------------
# Classification schemes
# ---------------------------------------------------------------------------


class IndustryClassificationScheme(StrEnum):
    """Named industry/sector taxonomies supported by :class:`IndustryClassification`."""

    SIC = "sic"
    NAICS = "naics"
    GICS = "gics"
    TRBC = "trbc"
    ICB = "icb"
    BICS = "bics"
    NACE = "nace"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Filings
# ---------------------------------------------------------------------------


class FilingType(StrEnum):
    """Canonical SEC/regulatory filing types.

    Values map 1:1 to the ``form`` column stored in ``sec_filings`` and its
    peers (``filing_type`` on new ``filing_events``).
    """

    ANNUAL_REPORT = "10-K"
    QUARTERLY_REPORT = "10-Q"
    CURRENT_REPORT = "8-K"
    INSIDER = "4"
    INSIDER_INITIAL = "3"
    INSIDER_AMEND = "5"
    PROXY = "DEF 14A"
    REGISTRATION_S1 = "S-1"
    REGISTRATION_S3 = "S-3"
    REGISTRATION_S4 = "S-4"
    FORM_13F_HR = "13F-HR"
    FORM_13F_NT = "13F-NT"
    FORM_13D = "SC 13D"
    FORM_13G = "SC 13G"
    NT10K = "NT 10-K"
    NT10Q = "NT 10-Q"
    FORM_144 = "144"
    PROSPECTUS = "424B"
    ANNUAL_REPORT_FOREIGN = "20-F"
    QUARTERLY_REPORT_FOREIGN = "6-K"
    ASR = "ASR"
    NPORT = "N-PORT"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Corporate actions
# ---------------------------------------------------------------------------


class CorporateActionKind(StrEnum):
    SPLIT = "split"
    REVERSE_SPLIT = "reverse_split"
    DIVIDEND = "dividend"
    STOCK_DIVIDEND = "stock_dividend"
    SPIN_OFF = "spin_off"
    MERGER = "merger"
    ACQUISITION = "acquisition"
    TENDER = "tender"
    NAME_CHANGE = "name_change"
    SYMBOL_CHANGE = "symbol_change"
    DELISTING = "delisting"
    RELISTING = "relisting"
    IPO = "ipo"
    SECONDARY_OFFERING = "secondary_offering"
    RIGHTS_ISSUE = "rights_issue"
    BONUS_ISSUE = "bonus_issue"
    BUYBACK = "buyback"
    BANKRUPTCY = "bankruptcy"
    EXCHANGE_OFFER = "exchange_offer"
    WARRANT_EXERCISE = "warrant_exercise"
