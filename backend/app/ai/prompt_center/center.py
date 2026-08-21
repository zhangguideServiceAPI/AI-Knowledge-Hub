"""文件型 Prompt Center 的加载、校验、缓存与渲染逻辑。

目录约定如下，每个 Prompt 版本必须同时包含元数据和正文：

    prompts/
      assistant/              # prompt_key
        v1/                   # version
          metadata.toml       # 身份和变量契约
          template.md         # Prompt 正文

示例一：项目内置的 ``assistant/v1`` 没有声明变量，因此必须传入空字典：

    center = PromptCenter()
    center.preload()  # 应用启动时校验并缓存全部模板
    assistant_prompt = center.render(
        prompt_key="assistant",
        version="v1",
        variables={},
    )
    system_message = assistant_prompt.content

示例二：项目中的 ``summary/v1/metadata.toml`` 声明了两个必填变量：

    required_variables = ["language", "style"]

并且 ``template.md`` 中使用了相同的占位符：

    Write the summary in {language} using a {style} style.

调用时必须同时提供 ``language`` 和 ``style``，不能缺少或额外增加变量：

    summary_prompt = center.render(
        prompt_key="summary",
        version="v1",
        variables={
            "language": "Chinese",
            "style": "concise",
        },
    )
    # summary_prompt.content 已将 {language} 和 {style} 替换为上面的值。

示例三：项目中的 ``translation/v1`` 模板声明了三个不同的必填变量：

    required_variables = ["source_language", "target_language", "tone"]

对应的模板正文：

    Translate the user's content from {source_language} to {target_language}
    using a {tone} tone.

对应的调用参数：

    translation_prompt = center.render(
        prompt_key="translation",
        version="v1",
        variables={
            "source_language": "English",
            "target_language": "Chinese",
            "tone": "professional",
        },
    )
    # translation_prompt.content 已替换三个占位符，变量值不会被二次渲染。

示例二和示例三既是学习示例，也是真实可加载的 Prompt 资产，但仅仅存在于目录中不会
让业务自动使用它们。ChatService 必须显式选择对应的 ``prompt_key + version``。变量
字典的 Key 必须与 ``metadata.toml`` 及 ``template.md`` 中的变量名完全一致；少传、
多传或传入非字符串 Value 都会抛出 ``PromptVariableError``。

``render()`` 不会自动选择最新版，也不会在版本不存在时回退。调用方必须显式提供
``prompt_key + version``，保证相同业务输入始终能定位到确定的 Prompt 契约。
"""

from collections.abc import Mapping
from pathlib import Path
from string import Formatter
import re
import tomllib

from app.ai.prompt_center.exceptions import (
    PromptConfigurationError,
    PromptNotFoundError,
    PromptVariableError,
    PromptVersionNotFoundError,
)
from app.ai.prompt_center.models import PromptTemplate, RenderedPrompt

_PROMPT_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_VARIABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_METADATA_FIELDS = frozenset(
    {
        "prompt_key",
        "version",
        "required_variables",
    }
)
_DEFAULT_PROMPTS_ROOT = Path(__file__).resolve().parents[1] / "prompts"
# Path(__file__)
# # /backend/app/ai/prompt_center/center.py

# Path(__file__).resolve()
# # 得到规范的绝对路径

# Path(__file__).resolve().parents[0]
# # /backend/app/ai/prompt_center

# Path(__file__).resolve().parents[1]
# # /backend/app/ai

# Path(__file__).resolve().parents[1] / "prompts"
# # /backend/app/ai/prompts

class PromptCenter:
    """管理版本化 Prompt 模板，并为调用方生成最终 Prompt。

    Args:
        prompts_root: Prompt 根目录。传入 ``None`` 时使用应用内置的 ``ai/prompts``；
            测试可以传入临时目录，隔离真实 Prompt 资产。

    ``Path | None`` 是联合类型，表示参数可以是 ``Path``，也可以是 ``None``。
    构造函数只准备路径和空缓存；若要在应用启动阶段一次发现所有错误，应继续调用
    ``preload()``。
    """

    def __init__(self, prompts_root: Path | None = None) -> None:
        # ``resolve()`` 把相对路径转为规范的绝对路径，使默认目录不受进程当前工作
        # 目录影响。后续仍会拒绝符号链接和非法标识，避免从预期目录跳到其他位置。
        self._prompts_root = (
            _DEFAULT_PROMPTS_ROOT if prompts_root is None else prompts_root
        ).resolve()

        # ``dict[tuple[str, str], PromptTemplate]`` 表示：字典 Key 是
        # ``(prompt_key, version)`` 两个字符串组成的元组，Value 是已校验模板。
        # 缓存模板而不缓存渲染结果，避免把不同请求的变量值长期保留在内存中。
        self._template_cache: dict[tuple[str, str], PromptTemplate] = {}

    def preload(self) -> None:
        """扫描并校验全部可见 Prompt，将合法模板放入内存缓存。

        应在应用启动时调用。任何目录、元数据或模板错误都会抛出
        ``PromptConfigurationError``，让错误配置尽早阻止服务启动，而不是等到真实
        用户请求时才暴露。

        名字以 ``.`` 开头的系统隐藏项会忽略；其他未知文件、空目录、符号链接或非法
        目录名都会失败，防止错误文件悄悄混入 Prompt 资产目录。
        """

        if not self._prompts_root.is_dir():
            raise PromptConfigurationError("Prompt root is not available.")
                            # sorted() 按路径名称排序。
        prompt_directories = sorted(
            path
            for path in self._prompts_root.iterdir()
            if not path.name.startswith(".")
        )
        if not prompt_directories:
            raise PromptConfigurationError("Prompt root does not contain any prompts.")

        for prompt_directory in prompt_directories:
            if (
                not prompt_directory.is_dir()
                or prompt_directory.is_symlink() # 符号链接可以理解为指向另一个文件或目录的快捷入口。 prompts/summary -> /other/private/directory
                or not _is_prompt_identifier(prompt_directory.name)
            ):
                raise PromptConfigurationError("Prompt root contains an invalid entry.")

            version_directories = sorted(
                path
                for path in prompt_directory.iterdir()
                if not path.name.startswith(".")
            )
            if not version_directories:
                raise PromptConfigurationError("Prompt does not contain any versions.")

            for version_directory in version_directories:
                if (
                    not version_directory.is_dir()
                    or version_directory.is_symlink()
                    or not _is_prompt_identifier(version_directory.name)
                ):
                    raise PromptConfigurationError(
                        "Prompt contains an invalid version entry."
                    )

                self._get_template(
                    prompt_directory.name,
                    version_directory.name,
                )

    def render(
        self,
        prompt_key: str,
        version: str,
        variables: Mapping[str, str],
    ) -> RenderedPrompt:
        """定位一个模板、严格校验变量并返回渲染结果。

        Args:
            prompt_key: Prompt 的业务标识，对应一级目录名，例如 ``assistant``。
            version: 显式版本，对应二级目录名，例如 ``v1``。
            variables: 模板变量。``Mapping[str, str]`` 表示任何“字符串映射到字符串”
                的只读接口都可传入，普通 ``dict[str, str]`` 就满足该接口。

        Returns:
            新创建的 ``RenderedPrompt``。每次调用都会生成新结果，不从缓存复用正文。

        Raises:
            PromptNotFoundError: Prompt Key 不存在或不合法。
            PromptVersionNotFoundError: 版本不存在或不合法。
            PromptConfigurationError: 磁盘中的 Prompt 资产配置错误。
            PromptVariableError: 变量缺少、多余，或 Key/Value 不是字符串。
        """

        template = self._get_template(prompt_key, version)
        rendered_content = _render_template(template, variables)

        return RenderedPrompt(
            prompt_key=template.prompt_key,
            version=template.version,
            content=rendered_content,
        )

    def _get_template(self, prompt_key: str, version: str) -> PromptTemplate:
        """优先从缓存取模板；缓存未命中时才从磁盘加载并校验。"""

        cache_key = (prompt_key, version)
        cached_template = self._template_cache.get(cache_key)

        if cached_template is not None:
            return cached_template

        template = self._load_template(prompt_key, version)
        self._template_cache[cache_key] = template
        return template

    def _load_template(self, prompt_key: str, version: str) -> PromptTemplate:
        """读取指定版本的两个文件，并构造经过完整校验的模板对象。"""

        # 先验证目录标识，再拼接路径。这样 ``../secret``、绝对路径等输入不会被当作
        # 文件系统路径使用。不存在和格式非法统一返回安全错误，不泄露真实目录结构。
        if not _is_prompt_identifier(prompt_key):
            raise PromptNotFoundError("Prompt key is not available.")

        prompt_directory = self._prompts_root / prompt_key
        if not prompt_directory.is_dir() or prompt_directory.is_symlink():
            raise PromptNotFoundError("Prompt key is not available.")

        if not _is_prompt_identifier(version):
            raise PromptVersionNotFoundError("Prompt version is not available.")

        version_directory = prompt_directory / version
        if not version_directory.is_dir() or version_directory.is_symlink():
            raise PromptVersionNotFoundError("Prompt version is not available.")

        metadata = _read_metadata(version_directory / "metadata.toml")
        template_text = _read_template(version_directory / "template.md")

        return _build_template(
            metadata,
            template_text=template_text,
            expected_prompt_key=prompt_key,
            expected_version=version,
        )


def _is_prompt_identifier(value: object) -> bool:
    """判断 Key/Version 是否是安全的单段目录名。

    参数使用 ``object``，表示运行时可能收到任何类型；只有字符串且完全匹配正则才
    返回 ``True``。``fullmatch`` 要求整个字符串符合规则，不接受只匹配一部分的值。
    """

    return (
        isinstance(value, str)
        and _PROMPT_IDENTIFIER_PATTERN.fullmatch(value) is not None
    )


def _read_metadata(path: Path) -> dict[str, object]:
    """用 Python 标准库 ``tomllib`` 读取 TOML 元数据。"""

    if not path.is_file() or path.is_symlink():
        raise PromptConfigurationError("Prompt metadata is not a regular file.")

    try:
        with path.open("rb") as metadata_file:
            metadata = tomllib.load(metadata_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        # ``raise ... from error`` 称为异常链：对外只暴露领域异常，调试时仍可看到底层
        # 原因。领域异常文本不拼接原始错误，避免路径或文件内容进入 HTTP 响应。
        raise PromptConfigurationError(
            "Prompt metadata could not be loaded."
        ) from error

    if not isinstance(metadata, dict):
        raise PromptConfigurationError("Prompt metadata must be a TOML table.")

    return metadata


def _read_template(path: Path) -> str:
    """按 UTF-8 读取非空模板正文，并拒绝符号链接。"""

    if not path.is_file() or path.is_symlink():
        raise PromptConfigurationError("Prompt template is not a regular file.")

    try:
        template_text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise PromptConfigurationError(
            "Prompt template could not be loaded."
        ) from error

    if not template_text.strip():
        raise PromptConfigurationError("Prompt template must not be blank.")

    return template_text


def _build_template(
    metadata: dict[str, object],
    *,
    template_text: str,
    expected_prompt_key: str,
    expected_version: str,
) -> PromptTemplate:
    """交叉校验目录、元数据和模板正文，建立可信的模板契约。"""

    # ``frozenset(metadata)`` 得到不可变的字段名集合。使用“完全相等”意味着缺少字段
    # 和出现未知字段都会失败，避免拼写错误被静默忽略。
    if frozenset(metadata) != _METADATA_FIELDS:
        raise PromptConfigurationError("Prompt metadata fields are invalid.")

    prompt_key = metadata["prompt_key"]
    version = metadata["version"]
    raw_required_variables = metadata["required_variables"]

    if prompt_key != expected_prompt_key or version != expected_version:
        raise PromptConfigurationError("Prompt metadata does not match its directory.")

    if not _is_prompt_identifier(prompt_key) or not _is_prompt_identifier(version):
        raise PromptConfigurationError("Prompt metadata identifiers are invalid.")

    required_variables = _parse_required_variables(raw_required_variables)
    template_variables = _extract_template_variables(template_text)

    if template_variables != required_variables:
        raise PromptConfigurationError(
            "Prompt template variables do not match its metadata."
        )

    return PromptTemplate(
        prompt_key=prompt_key,
        version=version,
        required_variables=required_variables,
        template=template_text,
    )


def _parse_required_variables(value: object) -> frozenset[str]:
    """把 TOML 变量列表转换成已校验、去重且不可变的集合。"""

    if not isinstance(value, list):
        raise PromptConfigurationError("Prompt required_variables must be a list.")

    if any(
        not isinstance(variable, str)
        or _VARIABLE_NAME_PATTERN.fullmatch(variable) is None
        for variable in value
    ):
        raise PromptConfigurationError("Prompt required variable names are invalid.")

    required_variables = frozenset(value)
    # ``frozenset`` 会自动合并重复项，因此比较转换前后的长度即可发现重复声明。
    if len(required_variables) != len(value):
        raise PromptConfigurationError("Prompt required variable names must be unique.")

    return required_variables


def _extract_template_variables(template: str) -> frozenset[str]:
    """解析模板占位符，并只允许简单的 ``{variable}`` 语法。

    ``Formatter.parse()`` 不会执行模板，而是逐段返回四元组：普通文本、变量名、格式
    说明符和转换标记。我们借此拒绝 ``{user.name}``、``{items[0]}``、``{x!r}``、
    ``{x:>10}`` 等复杂语法，只保留容易审计的变量替换。
    """

    variables: set[str] = set()

    try:
        parsed_fields = Formatter().parse(template)
        for _literal, field_name, format_spec, conversion in parsed_fields:
            if field_name is None:
                continue

            if (
                _VARIABLE_NAME_PATTERN.fullmatch(field_name) is None
                or format_spec
                or conversion is not None
            ):
                raise PromptConfigurationError(
                    "Prompt template contains an unsupported placeholder."
                )

            variables.add(field_name)
    except ValueError as error:
        raise PromptConfigurationError(
            "Prompt template contains malformed placeholders."
        ) from error

    return frozenset(variables)


def _render_template(
    template: PromptTemplate,
    variables: Mapping[str, str],
) -> str:
    """按模板声明精确校验变量，并执行一次字符串替换。

    变量集合必须与 ``required_variables`` 完全相等：缺少变量会导致模板不完整，多余
    变量通常意味着调用方拼写错误或契约已经漂移，两者都不能静默接受。
    """

    if not isinstance(variables, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in variables.items()
    ):
        raise PromptVariableError("Prompt variables must map strings to strings.")

    if frozenset(variables) != template.required_variables:
        raise PromptVariableError(
            "Prompt variables do not match the template contract."
        )

    # ``format_map`` 只解析模板本身一次。变量值即使包含 ``{secret}``，也只是普通
    # 字符串，不会被当成第二层模板再次展开。
    # "Write in {language} using a {style} style.".format_map(
    #     {
    #         "language": "Chinese",
    #         "style": "concise",
    #     }
    #  )
    return template.template.format_map(dict(variables))
