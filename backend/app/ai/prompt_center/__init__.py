"""Prompt Center 的公开导入入口。

业务代码应从 ``app.ai.prompt_center`` 导入公开类型，而不是依赖 ``center.py``、
``models.py`` 等内部文件的位置。例如：

    from app.ai.prompt_center import PromptCenter, PromptError

这样以后即使内部文件重新组织，只要这里的公开契约不变，调用方就无需修改。
"""

from app.ai.prompt_center.center import PromptCenter
from app.ai.prompt_center.exceptions import (
    PromptConfigurationError,
    PromptError,
    PromptNotFoundError,
    PromptVariableError,
    PromptVersionNotFoundError,
)
from app.ai.prompt_center.factory import get_prompt_center
from app.ai.prompt_center.models import PromptTemplate, RenderedPrompt

__all__ = [
    "PromptCenter",
    "PromptConfigurationError",
    "PromptError",
    "PromptNotFoundError",
    "PromptTemplate",
    "PromptVariableError",
    "PromptVersionNotFoundError",
    "RenderedPrompt",
    "get_prompt_center",
]

# ``__all__`` 明确声明这个包对外承诺的名称。它既是公开 API 清单，也会控制
# ``from app.ai.prompt_center import *`` 时导出的内容；业务代码仍建议显式导入名称。
