"""Precision-safe money/price/quantity value objects.

Inspired by nautilus_trader's ``Money``/``Price``/``Quantity`` scalars. Each
wraps a :class:`decimal.Decimal` so arithmetic stays exact under standard
accounting rounding; each is frozen/hashable and exposes ``as_decimal`` /
``as_float`` / ``from_str`` helpers. A :class:`Currency` dataclass carries the
ISO/crypto code, precision, and ``is_fiat``/``is_crypto`` flags so callers
reaching for ``Money("0.000004321", BTC)`` don't have to worry about losing
precision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Currency:
    """A monetary unit with known precision.

    Used by :class:`Money` / :class:`Price` / :class:`Quantity` to enforce
    proper rounding and as the key in :class:`aqp.core.types.CashBook`.
    """

    code: str
    precision: int = 2
    name: str = ""
    is_fiat: bool = True
    is_crypto: bool = False
    iso_numeric: int | None = None

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("Currency.code must be non-empty")

    def __str__(self) -> str:
        return self.code

    def quantize(self, value: Decimal) -> Decimal:
        """Round ``value`` to this currency's precision."""
        q = Decimal(1).scaleb(-self.precision)
        return value.quantize(q)


# Module-level cache of well-known currencies so identity comparisons work.
_CURRENCY_CACHE: dict[str, Currency] = {}


def _cur(
    code: str,
    precision: int,
    *,
    name: str = "",
    is_fiat: bool = True,
    is_crypto: bool = False,
    iso_numeric: int | None = None,
) -> Currency:
    c = Currency(
        code=code,
        precision=precision,
        name=name or code,
        is_fiat=is_fiat,
        is_crypto=is_crypto,
        iso_numeric=iso_numeric,
    )
    _CURRENCY_CACHE[code] = c
    return c


# Fiat (selected, expand as needed).
USD = _cur("USD", 2, name="US Dollar", iso_numeric=840)
EUR = _cur("EUR", 2, name="Euro", iso_numeric=978)
GBP = _cur("GBP", 2, name="British Pound", iso_numeric=826)
JPY = _cur("JPY", 0, name="Japanese Yen", iso_numeric=392)
CNY = _cur("CNY", 2, name="Chinese Yuan", iso_numeric=156)
HKD = _cur("HKD", 2, name="Hong Kong Dollar", iso_numeric=344)
CAD = _cur("CAD", 2, name="Canadian Dollar", iso_numeric=124)
AUD = _cur("AUD", 2, name="Australian Dollar", iso_numeric=36)
CHF = _cur("CHF", 2, name="Swiss Franc", iso_numeric=756)
SGD = _cur("SGD", 2, name="Singapore Dollar", iso_numeric=702)
INR = _cur("INR", 2, name="Indian Rupee", iso_numeric=356)
KRW = _cur("KRW", 0, name="South Korean Won", iso_numeric=410)

# Crypto.
BTC = _cur("BTC", 8, name="Bitcoin", is_fiat=False, is_crypto=True)
ETH = _cur("ETH", 18, name="Ethereum", is_fiat=False, is_crypto=True)
USDT = _cur("USDT", 6, name="Tether", is_fiat=False, is_crypto=True)
USDC = _cur("USDC", 6, name="USD Coin", is_fiat=False, is_crypto=True)


@lru_cache(maxsize=None)
def currency_of(code: str) -> Currency:
    """Lookup/construct a :class:`Currency` for an ISO/crypto code.

    Unknown codes default to ``precision=2`` fiat. Cached so the same code
    always returns the same object (``is`` comparison works in hot loops).
    """
    upper = code.upper()
    if upper in _CURRENCY_CACHE:
        return _CURRENCY_CACHE[upper]
    # Heuristic: 3-char upper-case → treat as fiat; else crypto.
    is_crypto = not (len(upper) == 3 and upper.isalpha())
    default_precision = 8 if is_crypto else 2
    cur = Currency(
        code=upper,
        precision=default_precision,
        name=upper,
        is_fiat=not is_crypto,
        is_crypto=is_crypto,
    )
    _CURRENCY_CACHE[upper] = cur
    return cur


# ---------------------------------------------------------------------------
# Scalar value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _DecimalScalar:
    """Shared base for :class:`Price`/:class:`Quantity`/:class:`Money`."""

    raw: Decimal = field(default=Decimal("0"))
    precision: int = 8

    def __post_init__(self) -> None:
        if self.precision < 0:
            raise ValueError("precision must be non-negative")

    @property
    def as_decimal(self) -> Decimal:
        return self.raw

    @property
    def as_float(self) -> float:
        return float(self.raw)

    def __float__(self) -> float:
        return float(self.raw)

    def __str__(self) -> str:
        return format(self.raw, f".{self.precision}f")


def _to_decimal(value: Decimal | str | int | float) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class Price(_DecimalScalar):
    """A price with an explicit ``precision`` (ticks per whole)."""

    @classmethod
    def from_str(cls, value: str, precision: int = 8) -> Price:
        return cls(_to_decimal(value), precision=precision)

    @classmethod
    def of(cls, value: Decimal | str | int | float, precision: int = 8) -> Price:
        return cls(_to_decimal(value), precision=precision)

    def add(self, other: Price) -> Price:
        return Price(self.raw + other.raw, precision=max(self.precision, other.precision))

    def sub(self, other: Price) -> Price:
        return Price(self.raw - other.raw, precision=max(self.precision, other.precision))

    def mul(self, factor: Decimal | int | float) -> Price:
        return Price(self.raw * _to_decimal(factor), precision=self.precision)


@dataclass(frozen=True, slots=True)
class Quantity(_DecimalScalar):
    """A size / volume quantity (contracts, shares, base-asset units)."""

    @classmethod
    def from_str(cls, value: str, precision: int = 0) -> Quantity:
        return cls(_to_decimal(value), precision=precision)

    @classmethod
    def of(cls, value: Decimal | str | int | float, precision: int = 0) -> Quantity:
        return cls(_to_decimal(value), precision=precision)

    def add(self, other: Quantity) -> Quantity:
        return Quantity(self.raw + other.raw, precision=max(self.precision, other.precision))

    def sub(self, other: Quantity) -> Quantity:
        return Quantity(self.raw - other.raw, precision=max(self.precision, other.precision))

    def mul(self, factor: Decimal | int | float) -> Quantity:
        return Quantity(self.raw * _to_decimal(factor), precision=self.precision)


@dataclass(frozen=True, slots=True)
class Money:
    """A currency-aware amount.

    ``currency`` is mandatory; precision is sourced from the currency so
    ``Money(Decimal("0.00000001"), BTC)`` keeps its 8 decimals while
    ``Money(Decimal("10.005"), USD)`` quantizes to ``10.01``.
    """

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        # Normalize to currency precision at construction time.
        object.__setattr__(self, "amount", self.currency.quantize(self.amount))

    @classmethod
    def of(cls, amount: Decimal | str | int | float, currency: Currency | str) -> Money:
        cur = currency if isinstance(currency, Currency) else currency_of(currency)
        return cls(_to_decimal(amount), cur)

    @classmethod
    def zero(cls, currency: Currency | str) -> Money:
        return cls.of(0, currency)

    @property
    def as_decimal(self) -> Decimal:
        return self.amount

    @property
    def as_float(self) -> float:
        return float(self.amount)

    def __str__(self) -> str:
        return f"{format(self.amount, f'.{self.currency.precision}f')} {self.currency.code}"

    def add(self, other: Money) -> Money:
        _require_same_currency(self, other)
        return Money(self.amount + other.amount, self.currency)

    def sub(self, other: Money) -> Money:
        _require_same_currency(self, other)
        return Money(self.amount - other.amount, self.currency)

    def mul(self, factor: Decimal | int | float) -> Money:
        return Money(self.amount * _to_decimal(factor), self.currency)

    def neg(self) -> Money:
        return Money(-self.amount, self.currency)


def _require_same_currency(a: Money, b: Money) -> None:
    if a.currency.code != b.currency.code:
        raise ValueError(
            f"cannot operate on Money with different currencies: {a.currency.code} vs {b.currency.code}"
        )
