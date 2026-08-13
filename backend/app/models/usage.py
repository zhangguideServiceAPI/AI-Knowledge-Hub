"""AI Chat 请求的最终 Usage 审计记录。

一条 ``ChatUsage`` 对应一次客户端请求，而不是一次 Provider 重试或一个 SSE Event。
该表只保存可查询的元数据和资源消耗，不保存 Message、Prompt 正文、模型回答、
API Key 或 Provider 原始异常。
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatUsageErrorCode(StrEnum):
    """Usage 内部审计错误码，不等同于客户端公开错误码。"""

    INVALID_MODEL = "ai_invalid_model"
    INVALID_REQUEST = "ai_invalid_request"
    PROVIDER_RATE_LIMIT = "ai_provider_rate_limit"
    PROVIDER_TIMEOUT = "ai_provider_timeout"
    PROVIDER_UNAVAILABLE = "ai_provider_unavailable"
    PROMPT_ERROR = "ai_prompt_error"
    INTERNAL_ERROR = "ai_internal_error"
    CANCELLED = "ai_cancelled"


class ChatUsageMode(StrEnum):
    """区分普通响应和流式响应，避免把空 TTFT 的含义混在一起。"""

    NON_STREAM = "non_stream"
    STREAM = "stream"


class ChatUsageStatus(StrEnum):
    """一次 Chat 请求最终只能进入其中一个终态。"""

    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChatUsage(Base):
    """一次 AI Chat 请求结束后的资源消耗和终态快照。"""

    __tablename__ = "chat_usages"

    # __table_args__ 用来声明不能只写在某一个 mapped_column 上的表级规则，
    # 包括唯一约束、复合索引和需要同时判断多个字段的检查约束。
    __table_args__ = (
        # 同一个客户端请求只能生成一条最终 Usage，避免重复写入和重复计费。
        UniqueConstraint(
            "request_id",
            name="uq_chat_usages_request_id",
        ),
        # 加速“查询某个用户最近 Usage”的列表查询。
        # 复合索引按 user_id 过滤，再按 created_at 排序；字段顺序必须匹配查询方式。
        Index(
            "ix_chat_usages_user_created_at",
            "user_id",
            "created_at",
        ),
        # 加速按终态筛选并按时间分析 Usage，例如查看最近失败的请求。
        Index(
            "ix_chat_usages_status_created_at",
            "status",
            "created_at",
        ),
        # request_mode 只允许稳定契约定义的普通响应或流式响应。
        CheckConstraint(
            "request_mode IN ('non_stream', 'stream')",
            name="ck_chat_usages_request_mode",
        ),
        # status 只允许请求生命周期定义的三个终态。
        CheckConstraint(
            "status IN ('success', 'failed', 'cancelled')",
            name="ck_chat_usages_status",
        ),
        # Token 为 NULL 表示 Provider 没返回可信统计；已知时不能是负数。
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_chat_usages_input_tokens_non_negative",
        ),
        # 输出 Token 采用同样的“未知或非负”规则。
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_chat_usages_output_tokens_non_negative",
        ),
        # 总 Token 采用同样的“未知或非负”规则。
        CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="ck_chat_usages_total_tokens_non_negative",
        ),
        # 三个 Token 都已知时，总数必须等于输入加输出；任意一个未知时不伪造校验结果。
        CheckConstraint(
            "input_tokens IS NULL OR output_tokens IS NULL "
            "OR total_tokens IS NULL "
            "OR total_tokens = input_tokens + output_tokens",
            name="ck_chat_usages_token_total",
        ),
        # 总耗时从请求开始计算，不能出现负数。
        CheckConstraint(
            "latency_ms >= 0",
            name="ck_chat_usages_latency_ms_non_negative",
        ),
        # TTFT 可能因非流式请求或首 Event 前失败而未知；已知时不能是负数。
        CheckConstraint(
            "time_to_first_token_ms IS NULL OR time_to_first_token_ms >= 0",
            name="ck_chat_usages_ttft_ms_non_negative",
        ),
        # 成本可以暂不估算；一旦有值就不能是负数。
        CheckConstraint(
            "estimated_cost IS NULL OR estimated_cost >= 0",
            name="ck_chat_usages_estimated_cost_non_negative",
        ),
        # 成本、币种和价格版本必须同时为空或同时有值，保证成本快照可解释。
        CheckConstraint(
            "(estimated_cost IS NULL AND currency IS NULL "
            "AND pricing_version IS NULL) OR "
            "(estimated_cost IS NOT NULL AND currency IS NOT NULL "
            "AND pricing_version IS NOT NULL)",
            name="ck_chat_usages_cost_snapshot",
        ),
        # 成功必须记录模型结束原因且不能有错误码；失败或取消则必须记录错误码，
        # 同时不能伪造 finish_reason，防止相互矛盾的请求终态进入数据库。
        CheckConstraint(
            "(status = 'success' AND finish_reason IS NOT NULL "
            "AND error_code IS NULL) OR "
            "(status IN ('failed', 'cancelled') AND finish_reason IS NULL "
            "AND error_code IS NOT NULL)",
            name="ck_chat_usages_terminal_fields",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            # "users.id" 使用“目标表名.目标列名”定位被引用的主键列。
            "users.id",
            # name 是数据库中的外键约束名，便于 Migration、排错和以后显式删除约束。
            name="fk_chat_usages_user_id_users",
            # 删除 User 时由数据库拒绝操作，只要该用户仍有 Usage 审计记录。
            # 这是数据库行为，不等同于 SQLAlchemy ORM 的 relationship cascade。
            ondelete="RESTRICT",
        ),
        # nullable=False 约束当前表的 user_id 必须有值；ForeignKey 则约束该值必须存在于 users.id。
        nullable=False,
    )

    request_mode: Mapped[str] = mapped_column(String(16), nullable=False)

    # 路由或 Prompt 在 Provider 选择前失败时，下列模型字段可能尚不可知。
    model_alias: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 列名使用 Usage 契约中的 provider；值是内部 Provider Key。
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Provider 没有返回可信 Usage 时保存 NULL，不能用 0 表示未知。
    input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    latency_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    time_to_first_token_ms: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    finish_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Numeric 在 Python 中映射为 Decimal，避免 float 的二进制金额误差。
    estimated_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 10),
        nullable=True,
    )
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    pricing_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # created_at 表示请求开始时间，Service 可以显式传入；server_default 是兜底值。
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
