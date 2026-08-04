from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.file_resource import FileResource, FileStatus
from app.schemas.file import (
    FileResourceListResponse,
    FileResourceResponse,
)


def _build_resource() -> FileResource:
    return FileResource(
        id=str(uuid4()),
        owner_id=42,
        storage_provider="local",
        bucket="local",
        object_key="users/42/internal.bin",
        original_filename="report.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        sha256="a" * 64,
        status=FileStatus.READY.value,
        failure_reason=None,
        created_at=datetime(2026, 8, 4, 10, 0),
        updated_at=datetime(2026, 8, 4, 10, 0),
        deleted_at=None,
    )


def test_file_resource_response_hides_internal_fields() -> None:
    response = FileResourceResponse.model_validate(_build_resource())
    payload = response.model_dump(mode="json")

    assert payload["status"] == FileStatus.READY.value
    assert set(payload) == {
        "id",
        "original_filename",
        "content_type",
        "size_bytes",
        "status",
        "created_at",
        "updated_at",
    }

    assert "owner_id" not in payload
    assert "object_key" not in payload
    assert "sha256" not in payload


# 分页 Response 测试
def test_file_resource_list_response_contains_pagination() -> None:
    item = FileResourceResponse.model_validate(_build_resource())

    response = FileResourceListResponse(
        items=[item],
        limit=20,
        offset=0,
    )

    assert response.items == [item]
    assert response.limit == 20
    assert response.offset == 0


# 分页参数保护测试
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("limit", 0),
        ("offset", -1),
    ],
)
def test_file_resource_list_rejects_invalid_pagination(
    field: str,
    value: int,
) -> None:
    values = {
        "items": [],
        "limit": 20,
        "offset": 0,
    }
    values[field] = value

    with pytest.raises(ValidationError):
        FileResourceListResponse(**values)
