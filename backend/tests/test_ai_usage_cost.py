from decimal import Decimal

from app.ai.provider import TokenUsage
from app.ai.usage_cost import CostSnapshot, calculate_cost_snapshot
from app.core.config import AIModelPricingConfig


def _pricing() -> AIModelPricingConfig:
    return AIModelPricingConfig(
        input_price_per_million_tokens=Decimal("2.5"),
        output_price_per_million_tokens=Decimal("10"),
        currency="USD",
        version="2026-08-13",
    )


def test_calculate_cost_snapshot_uses_decimal_prices_and_fixed_scale() -> None:
    snapshot = calculate_cost_snapshot(
        _pricing(),
        TokenUsage(
            input_tokens=1000,
            output_tokens=250,
            total_tokens=1250,
        ),
    )

    assert snapshot == CostSnapshot(
        estimated_cost=Decimal("0.0050000000"),
        currency="USD",
        pricing_version="2026-08-13",
    )


def test_calculate_cost_snapshot_rounds_half_up_to_database_scale() -> None:
    pricing = AIModelPricingConfig(
        input_price_per_million_tokens=Decimal("0.00005"),
        output_price_per_million_tokens=Decimal("0"),
        currency="USD",
        version="tiny-price",
    )

    snapshot = calculate_cost_snapshot(
        pricing,
        TokenUsage(input_tokens=1, output_tokens=0, total_tokens=1),
    )

    assert snapshot is not None
    assert snapshot.estimated_cost == Decimal("0.0000000001")


def test_calculate_cost_snapshot_requires_pricing_and_input_output_tokens() -> None:
    complete_usage = TokenUsage(
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
    )

    assert calculate_cost_snapshot(None, complete_usage) is None
    assert calculate_cost_snapshot(_pricing(), None) is None
    assert (
        calculate_cost_snapshot(
            _pricing(),
            TokenUsage(input_tokens=None, output_tokens=20, total_tokens=None),
        )
        is None
    )
    assert (
        calculate_cost_snapshot(
            _pricing(),
            TokenUsage(input_tokens=10, output_tokens=None, total_tokens=None),
        )
        is None
    )
