from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch
import os

import pytest

from app.ai.exceptions import AIError, ProviderError
from app.ai.prompt_center import (
    PromptCenter,
    PromptConfigurationError,
    PromptError,
    PromptNotFoundError,
    PromptTemplate,
    PromptVariableError,
    PromptVersionNotFoundError,
    RenderedPrompt,
    get_prompt_center,
)
from app.ai.prompt_center import factory as prompt_center_factory


def _write_prompt(
    prompts_root: Path,
    *,
    prompt_key: str = "summary",
    version: str = "v1",
    required_variables: tuple[str, ...] = ("language", "style"),
    template: str = "Summarize in {language} with a {style} style.",
    metadata_prompt_key: str | None = None,
    metadata_version: str | None = None,
    extra_metadata: str = "",
) -> Path:
    version_directory = prompts_root / prompt_key / version
    version_directory.mkdir(parents=True)
    variables = ", ".join(f'"{variable}"' for variable in required_variables)
    metadata = (
        f'prompt_key = "{metadata_prompt_key or prompt_key}"\n'
        f'version = "{metadata_version or version}"\n'
        f"required_variables = [{variables}]\n"
        f"{extra_metadata}"
    )
    (version_directory / "metadata.toml").write_text(metadata, encoding="utf-8")
    (version_directory / "template.md").write_text(template, encoding="utf-8")
    return version_directory


def test_prompt_contracts_are_immutable() -> None:
    template = PromptTemplate(
        prompt_key="summary",
        version="v1",
        required_variables=frozenset({"language"}),
        template="Summarize in {language}.",
    )
    rendered = RenderedPrompt(
        prompt_key="summary",
        version="v1",
        content="Summarize in Chinese.",
    )

    with pytest.raises(FrozenInstanceError):
        template.version = "v2"

    with pytest.raises(FrozenInstanceError):
        rendered.content = "changed"


@pytest.mark.parametrize(
    "error_type",
    [
        PromptNotFoundError,
        PromptVersionNotFoundError,
        PromptConfigurationError,
        PromptVariableError,
    ],
)
def test_prompt_errors_use_independent_error_base(
    error_type: type[PromptError],
) -> None:
    error = error_type()

    assert isinstance(error, PromptError)
    assert not isinstance(error, AIError)
    assert not isinstance(error, ProviderError)


def test_render_loads_versioned_template_and_returns_identity(tmp_path: Path) -> None:
    _write_prompt(tmp_path)
    center = PromptCenter(tmp_path)

    rendered = center.render(
        "summary",
        "v1",
        {
            "language": "Chinese",
            "style": "concise",
        },
    )

    assert rendered == RenderedPrompt(
        prompt_key="summary",
        version="v1",
        content="Summarize in Chinese with a concise style.",
    )


def test_render_uses_default_prompt_root_independent_of_working_directory(
    tmp_path: Path,
) -> None:
    original_working_directory = Path.cwd()

    try:
        os.chdir(tmp_path)
        rendered = PromptCenter().render("assistant", "v1", {})
    finally:
        os.chdir(original_working_directory)

    assert rendered.prompt_key == "assistant"
    assert rendered.version == "v1"
    assert "AI-Knowledge-Hub" in rendered.content


@pytest.mark.parametrize(
    ("prompt_key", "version", "variables", "expected_content"),
    [
        (
            "summary",
            "v1",
            {"language": "Chinese", "style": "concise"},
            "Write the summary in Chinese using a concise style.",
        ),
        (
            "translation",
            "v1",
            {
                "source_language": "English",
                "target_language": "Chinese",
                "tone": "professional",
            },
            (
                "Translate the user's content from English to Chinese using a\n"
                "professional tone."
            ),
        ),
    ],
)
def test_render_loads_builtin_prompt_examples(
    prompt_key: str,
    version: str,
    variables: dict[str, str],
    expected_content: str,
) -> None:
    rendered = PromptCenter().render(prompt_key, version, variables)

    assert rendered.prompt_key == prompt_key
    assert rendered.version == version
    assert expected_content in rendered.content


def test_render_only_interprets_placeholders_from_template(tmp_path: Path) -> None:
    _write_prompt(
        tmp_path,
        required_variables=("language",),
        template="Summarize in {language}.",
    )
    center = PromptCenter(tmp_path)

    rendered = center.render(
        "summary",
        "v1",
        {"language": "Chinese {secret}"},
    )

    assert rendered.content == "Summarize in Chinese {secret}."


def test_render_supports_escaped_literal_braces(tmp_path: Path) -> None:
    _write_prompt(
        tmp_path,
        required_variables=("language",),
        template="Return {{literal}} in {language}.",
    )

    rendered = PromptCenter(tmp_path).render(
        "summary",
        "v1",
        {"language": "Chinese"},
    )

    assert rendered.content == "Return {literal} in Chinese."


@pytest.mark.parametrize(
    "variables",
    [
        {"language": "Chinese"},
        {
            "language": "Chinese",
            "style": "concise",
            "user_id": "42",
        },
        {"language": "Chinese", "style": 1},
    ],
)
def test_render_rejects_missing_extra_or_non_string_variables(
    tmp_path: Path,
    variables: dict[str, object],
) -> None:
    _write_prompt(tmp_path)

    with pytest.raises(PromptVariableError):
        PromptCenter(tmp_path).render(
            "summary",
            "v1",
            variables,  # type: ignore[arg-type]
        )


def test_render_rejects_unknown_prompt_without_using_unsafe_path(
    tmp_path: Path,
) -> None:
    _write_prompt(tmp_path)
    center = PromptCenter(tmp_path)

    with pytest.raises(PromptNotFoundError):
        center.render("../summary", "v1", {})


def test_render_distinguishes_unknown_version_from_unknown_prompt(
    tmp_path: Path,
) -> None:
    _write_prompt(tmp_path)
    center = PromptCenter(tmp_path)

    with pytest.raises(PromptVersionNotFoundError):
        center.render("summary", "v2", {})


@pytest.mark.parametrize(
    ("metadata_prompt_key", "metadata_version"),
    [
        ("translate", "v1"),
        ("summary", "v2"),
    ],
)
def test_load_rejects_metadata_identity_mismatch(
    tmp_path: Path,
    metadata_prompt_key: str,
    metadata_version: str,
) -> None:
    _write_prompt(
        tmp_path,
        metadata_prompt_key=metadata_prompt_key,
        metadata_version=metadata_version,
    )

    with pytest.raises(PromptConfigurationError):
        PromptCenter(tmp_path).render(
            "summary",
            "v1",
            {"language": "Chinese", "style": "concise"},
        )


@pytest.mark.parametrize(
    ("required_variables", "template"),
    [
        (("language", "style"), "Summarize in {language}."),
        (("language",), "Summarize in {language} with {style}."),
    ],
)
def test_load_rejects_declared_and_actual_variable_mismatch(
    tmp_path: Path,
    required_variables: tuple[str, ...],
    template: str,
) -> None:
    _write_prompt(
        tmp_path,
        required_variables=required_variables,
        template=template,
    )

    with pytest.raises(PromptConfigurationError):
        PromptCenter(tmp_path).render("summary", "v1", {})


@pytest.mark.parametrize(
    "template",
    [
        "Use {user.name}.",
        "Use {items[0]}.",
        "Use {language!r}.",
        "Use {language:>10}.",
        "Use {language.",
    ],
)
def test_load_rejects_complex_or_malformed_placeholders(
    tmp_path: Path,
    template: str,
) -> None:
    _write_prompt(
        tmp_path,
        required_variables=("language",),
        template=template,
    )

    with pytest.raises(PromptConfigurationError):
        PromptCenter(tmp_path).render("summary", "v1", {"language": "Chinese"})


@pytest.mark.parametrize(
    "metadata_content",
    [
        "not valid toml = [",
        'prompt_key = "summary"\nversion = "v1"\n',
        ('prompt_key = "summary"\nversion = "v1"\nrequired_variables = "language"\n'),
        (
            'prompt_key = "summary"\n'
            'version = "v1"\n'
            'required_variables = ["language", "language"]\n'
        ),
        (
            'prompt_key = "summary"\n'
            'version = "v1"\n'
            'required_variables = ["language"]\n'
            'description = "unexpected"\n'
        ),
    ],
)
def test_load_rejects_invalid_metadata(
    tmp_path: Path,
    metadata_content: str,
) -> None:
    version_directory = _write_prompt(
        tmp_path,
        required_variables=("language",),
        template="Use {language}.",
    )
    (version_directory / "metadata.toml").write_text(
        metadata_content,
        encoding="utf-8",
    )

    with pytest.raises(PromptConfigurationError):
        PromptCenter(tmp_path).render("summary", "v1", {"language": "Chinese"})


@pytest.mark.parametrize("missing_filename", ["metadata.toml", "template.md"])
def test_load_rejects_missing_prompt_file(
    tmp_path: Path,
    missing_filename: str,
) -> None:
    version_directory = _write_prompt(tmp_path)
    (version_directory / missing_filename).unlink()

    with pytest.raises(PromptConfigurationError):
        PromptCenter(tmp_path).render(
            "summary",
            "v1",
            {"language": "Chinese", "style": "concise"},
        )


@pytest.mark.parametrize("linked_filename", ["metadata.toml", "template.md"])
def test_load_rejects_symlinked_prompt_file(
    tmp_path: Path,
    linked_filename: str,
) -> None:
    version_directory = _write_prompt(tmp_path)
    linked_path = version_directory / linked_filename
    target_path = tmp_path / f"target-{linked_filename}"
    target_path.write_bytes(linked_path.read_bytes())
    linked_path.unlink()
    linked_path.symlink_to(target_path)

    with pytest.raises(PromptConfigurationError):
        PromptCenter(tmp_path).render(
            "summary",
            "v1",
            {"language": "Chinese", "style": "concise"},
        )


def test_load_rejects_blank_template(tmp_path: Path) -> None:
    _write_prompt(
        tmp_path,
        required_variables=(),
        template="   \n",
    )

    with pytest.raises(PromptConfigurationError):
        PromptCenter(tmp_path).render("summary", "v1", {})


def test_cache_keeps_validated_template_but_not_rendered_result(
    tmp_path: Path,
) -> None:
    version_directory = _write_prompt(
        tmp_path,
        required_variables=("language",),
        template="Original {language}.",
    )
    center = PromptCenter(tmp_path)

    first = center.render("summary", "v1", {"language": "Chinese"})
    (version_directory / "template.md").write_text(
        "Changed {language}.",
        encoding="utf-8",
    )
    second = center.render("summary", "v1", {"language": "English"})

    assert first.content == "Original Chinese."
    assert second.content == "Original English."


def test_preload_loads_every_version_into_template_cache(tmp_path: Path) -> None:
    first_directory = _write_prompt(
        tmp_path,
        version="v1",
        required_variables=("language",),
        template="Version one in {language}.",
    )
    second_directory = _write_prompt(
        tmp_path,
        version="v2",
        required_variables=("language",),
        template="Version two in {language}.",
    )
    center = PromptCenter(tmp_path)

    center.preload()
    (first_directory / "template.md").write_text(
        "Changed one in {language}.",
        encoding="utf-8",
    )
    (second_directory / "template.md").write_text(
        "Changed two in {language}.",
        encoding="utf-8",
    )

    assert center.render("summary", "v1", {"language": "Chinese"}).content == (
        "Version one in Chinese."
    )
    assert center.render("summary", "v2", {"language": "English"}).content == (
        "Version two in English."
    )


@pytest.mark.parametrize("invalid_entry", ["README.md", "invalid.prompt"])
def test_preload_rejects_invalid_prompt_root_entry(
    tmp_path: Path,
    invalid_entry: str,
) -> None:
    _write_prompt(tmp_path)
    (tmp_path / invalid_entry).write_text("unexpected", encoding="utf-8")

    with pytest.raises(PromptConfigurationError):
        PromptCenter(tmp_path).preload()


def test_preload_rejects_missing_or_empty_prompt_root(tmp_path: Path) -> None:
    with pytest.raises(PromptConfigurationError):
        PromptCenter(tmp_path / "missing").preload()

    with pytest.raises(PromptConfigurationError):
        PromptCenter(tmp_path).preload()


def test_preload_rejects_prompt_without_version(tmp_path: Path) -> None:
    (tmp_path / "summary").mkdir()

    with pytest.raises(PromptConfigurationError):
        PromptCenter(tmp_path).preload()


def test_preload_rejects_invalid_version_entry(tmp_path: Path) -> None:
    _write_prompt(tmp_path)
    (tmp_path / "summary" / "README.md").write_text(
        "unexpected",
        encoding="utf-8",
    )

    with pytest.raises(PromptConfigurationError):
        PromptCenter(tmp_path).preload()


def test_get_prompt_center_preloads_and_caches_default_center() -> None:
    get_prompt_center.cache_clear()

    try:
        with patch.object(
            prompt_center_factory.PromptCenter,
            "preload",
            autospec=True,
        ) as preload:
            first = get_prompt_center()
            second = get_prompt_center()
    finally:
        get_prompt_center.cache_clear()

    assert first is second
    preload.assert_called_once_with(first)
