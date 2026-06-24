from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PaymentMode = Literal["annual", "monthly"]

SENSOR_CLIENT_EUR = 540.0
SENSOR_PROVIDER_EUR = 325.0

_ANNUAL_BASE = 360.0
_ANNUAL_5_10 = 70.0
_ANNUAL_11_30 = 60.0
_ANNUAL_31_100 = 50.0
_ANNUAL_101_PLUS = 50.0

_MONTHLY_BASE = 45.0
_MONTHLY_5_10 = 9.0
_MONTHLY_11_30 = 7.5
_MONTHLY_31_100 = 6.0
_MONTHLY_101_PLUS = 6.0


@dataclass(frozen=True)
class PricingLine:
    label: str
    amount: float
    unit: str


@dataclass(frozen=True)
class SubscriptionResult:
    lines: list[PricingLine] = field(default_factory=list)
    subscription_total: float = 0.0
    custom_pricing_note: str | None = None


@dataclass(frozen=True)
class PricingQuote:
    mode: PaymentMode
    n_sensors: int
    subscription: SubscriptionResult
    hardware_total: float = 0.0
    hardware_line: PricingLine | None = None

    @property
    def grand_total(self) -> float:
        return round(self.subscription.subscription_total + self.hardware_total, 2)


def _tier_counts(n_sensors: int) -> tuple[int, int, int, int]:
    n = max(1, int(n_sensors))
    count_5_10 = max(0, min(n, 10) - 4)
    count_11_30 = max(0, min(n, 30) - 10)
    count_31_100 = max(0, min(n, 100) - 30)
    count_101_plus = max(0, n - 100)
    return count_5_10, count_11_30, count_31_100, count_101_plus


def compute_subscription(n_sensors: int, mode: PaymentMode) -> SubscriptionResult:
    n = max(1, int(n_sensors))
    count_5_10, count_11_30, count_31_100, count_101_plus = _tier_counts(n)

    if mode == "annual":
        base, r5, r11, r31, r101 = (
            _ANNUAL_BASE,
            _ANNUAL_5_10,
            _ANNUAL_11_30,
            _ANNUAL_31_100,
            _ANNUAL_101_PLUS,
        )
        unit = "€/año"
        base_label = "Base (hasta 4 sensores)"
    else:
        base, r5, r11, r31, r101 = (
            _MONTHLY_BASE,
            _MONTHLY_5_10,
            _MONTHLY_11_30,
            _MONTHLY_31_100,
            _MONTHLY_101_PLUS,
        )
        unit = "€/mes"
        base_label = "Base (hasta 4 sensores)"

    lines: list[PricingLine] = [PricingLine(base_label, base, unit)]
    total = base

    if count_5_10:
        amount = round(count_5_10 * r5, 2)
        total += amount
        lines.append(
            PricingLine(
                f"Sensores 5–10 ({count_5_10} × {r5:g} €)",
                amount,
                unit,
            )
        )
    if count_11_30:
        amount = round(count_11_30 * r11, 2)
        total += amount
        lines.append(
            PricingLine(
                f"Sensores 11–30 ({count_11_30} × {r11:g} €)",
                amount,
                unit,
            )
        )
    if count_31_100:
        amount = round(count_31_100 * r31, 2)
        total += amount
        lines.append(
            PricingLine(
                f"Sensores 31–100 ({count_31_100} × {r31:g} €)",
                amount,
                unit,
            )
        )
    if count_101_plus:
        amount = round(count_101_plus * r101, 2)
        total += amount
        lines.append(
            PricingLine(
                f"Sensores 101+ ({count_101_plus} × {r101:g} €)",
                amount,
                unit,
            )
        )

    note = None
    if n > 100:
        note = (
            "Más de 100 sensores: tarifa orientativa. "
            "Para volúmenes altos conviene precio a medida (p. ej. 60–65 €/sensor/año)."
        )

    return SubscriptionResult(
        lines=lines,
        subscription_total=round(total, 2),
        custom_pricing_note=note,
    )


def sensor_unit_price(*, provider_mode: bool) -> float:
    return SENSOR_PROVIDER_EUR if provider_mode else SENSOR_CLIENT_EUR


def compute_hardware(
    n_sensors: int,
    *,
    include_sensor: bool,
    provider_mode: bool,
) -> tuple[float, PricingLine | None]:
    if not include_sensor:
        return 0.0, None
    n = max(1, int(n_sensors))
    unit = sensor_unit_price(provider_mode=provider_mode)
    total = round(unit * n, 2)
    label = f"Sensor UC501 + Teros 10, 2 años de garantía ({n} × {unit:.0f} €)"
    return total, PricingLine(label, total, "€")


def compute_quote(
    n_sensors: int,
    mode: PaymentMode,
    *,
    include_sensor: bool = False,
    provider_mode: bool = False,
) -> PricingQuote:
    subscription = compute_subscription(n_sensors, mode)
    hardware_total, hardware_line = compute_hardware(
        n_sensors,
        include_sensor=include_sensor,
        provider_mode=provider_mode,
    )
    return PricingQuote(
        mode=mode,
        n_sensors=max(1, int(n_sensors)),
        subscription=subscription,
        hardware_total=hardware_total,
        hardware_line=hardware_line,
    )


@dataclass(frozen=True)
class SavingsComparison:
    annual_subscription: float
    monthly_subscription_per_month: float
    monthly_subscription_per_year: float
    savings_eur: float
    savings_pct: float


def compare_annual_vs_monthly(n_sensors: int) -> SavingsComparison:
    annual = compute_subscription(n_sensors, "annual").subscription_total
    monthly_per_month = compute_subscription(n_sensors, "monthly").subscription_total
    monthly_per_year = round(monthly_per_month * 12, 2)
    savings = round(monthly_per_year - annual, 2)
    pct = round((savings / monthly_per_year) * 100, 2) if monthly_per_year else 0.0
    return SavingsComparison(
        annual_subscription=annual,
        monthly_subscription_per_month=monthly_per_month,
        monthly_subscription_per_year=monthly_per_year,
        savings_eur=savings,
        savings_pct=pct,
    )
