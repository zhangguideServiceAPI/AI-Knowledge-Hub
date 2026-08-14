"""根据本次调用的 Token 与价格版本生成不可变成本快照。"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.ai.provider import TokenUsage
from app.core.config import AIModelPricingConfig

_TOKENS_PER_MILLION = Decimal("1000000")
_COST_SCALE = Decimal("0.0000000001")


@dataclass(frozen=True)
class CostSnapshot:
    """调用结束时的估算成本；它不会随未来价格配置变化。"""

    estimated_cost: Decimal
    currency: str
    pricing_version: str


def calculate_cost_snapshot(
    pricing: AIModelPricingConfig | None,
    usage: TokenUsage | None,
) -> CostSnapshot | None:
    """仅在价格和输入/输出 Token 都可信时计算成本。"""

    if (
        pricing is None
        or usage is None
        or usage.input_tokens is None
        or usage.output_tokens is None
    ):
        return None

    input_cost = Decimal(usage.input_tokens) * pricing.input_price_per_million_tokens
    output_cost = Decimal(usage.output_tokens) * pricing.output_price_per_million_tokens
    estimated_cost = ((input_cost + output_cost) / _TOKENS_PER_MILLION).quantize(
        _COST_SCALE,  # 最多保留小数点后 10 位
        rounding=ROUND_HALF_UP,  # 使用四舍五入
    )

    return CostSnapshot(
        estimated_cost=estimated_cost,
        currency=pricing.currency,
        pricing_version=pricing.version,
    )
