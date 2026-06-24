from __future__ import annotations

from services.pricing_calculator import (
    compare_annual_vs_monthly,
    compute_hardware,
    compute_quote,
    compute_subscription,
)


def test_annual_subscription_examples() -> None:
    assert compute_subscription(4, "annual").subscription_total == 360.0
    assert compute_subscription(8, "annual").subscription_total == 640.0
    assert compute_subscription(20, "annual").subscription_total == 1380.0
    assert compute_subscription(50, "annual").subscription_total == 2980.0
    assert compute_subscription(12, "annual").subscription_total == 900.0


def test_monthly_subscription_example() -> None:
    assert compute_subscription(12, "monthly").subscription_total == 114.0


def test_hardware_per_sensor() -> None:
    total, line = compute_hardware(8, include_sensor=True, provider_mode=False)
    assert total == 4320.0
    assert line is not None
    assert "8 ×" in line.label

    provider_total, _ = compute_hardware(8, include_sensor=True, provider_mode=True)
    assert provider_total == 2600.0


def test_full_quote_grand_total() -> None:
    quote = compute_quote(8, "annual", include_sensor=True, provider_mode=False)
    assert quote.subscription.subscription_total == 640.0
    assert quote.hardware_total == 4320.0
    assert quote.grand_total == 4960.0


def test_savings_12_sensors() -> None:
    cmp = compare_annual_vs_monthly(12)
    assert cmp.annual_subscription == 900.0
    assert cmp.monthly_subscription_per_month == 114.0
    assert cmp.monthly_subscription_per_year == 1368.0
    assert cmp.savings_eur == 468.0


def test_over_100_custom_note() -> None:
    result = compute_subscription(120, "annual")
    assert result.custom_pricing_note is not None
    # 360 + 6*70 + 20*60 + 70*50 + 20*50 = 360+420+1200+3500+1000 = 6480
    assert result.subscription_total == 6480.0
