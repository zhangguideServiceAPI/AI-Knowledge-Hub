from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.dependencies import (
    get_current_user,
    get_file_service,
    get_knowledge_indexing_components,
    get_knowledge_service,
)
from app.schemas.error import ErrorResponse
from app.schemas.knowledge import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseResponse,
    DocumentVersionResponse,
    KnowledgeDocumentResponse,
    KnowledgeFileIngestionResponse,
)
from app.schemas.user import UserResponse
from app.services.knowledge_service import (
    KnowledgeIndexingComponents,
    KnowledgeService,
)
from app.services.file_service import FileService


router = APIRouter(
    prefix="/knowledge-bases",
    tags=["Knowledge"],
)


@router.post(
    "",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Knowledge base could not be created.",
        },
    },
)
def create_knowledge_base(
    request: KnowledgeBaseCreateRequest,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    knowledge_service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> KnowledgeBaseResponse:
    """创建当前认证用户主动拥有的知识库，并返回创建后的元数据。"""

    return knowledge_service.create_base(
        owner_id=current_user.id,
        name=request.name,
    )


@router.put(
    "/{knowledge_base_id}/documents/{file_id}",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Knowledge base or file was not found.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Knowledge document could not be created.",
        },
    },
)
def add_file_to_knowledge_base(
    knowledge_base_id: str,
    file_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    knowledge_service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> KnowledgeDocumentResponse:
    """
    将一个 READY FileResource 主动加入当前用户的知识库。

    使用 PUT 是因为相同的 Base 与 File 重复请求应复用同一 Document；
    本接口只建立管理关系，不会读取文件或启动 Parse、Chunk、Embedding。
    """

    return knowledge_service.add_file_to_base(
        owner_id=current_user.id,
        knowledge_base_id=knowledge_base_id,
        file_id=file_id,
    )


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/versions/{document_version_id}/retry",
    response_model=DocumentVersionResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Knowledge document or version was not found.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "Document version cleanup is temporarily unavailable.",
        },
    },
)
async def retry_document_version(
    knowledge_base_id: str,
    document_id: str,
    document_version_id: str,
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    knowledge_service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
    components: Annotated[
        KnowledgeIndexingComponents,
        Depends(get_knowledge_indexing_components),
    ],
) -> DocumentVersionResponse:
    """
    重新执行一个失败 DocumentVersion 的索引，并返回其最新状态。

    客户端只指定已拥有知识库中的 Document 与 Version，不能直接改写状态；Service
    负责 failed 重排队、cleanup_required 的 Qdrant 清理和后续 Embedding/索引流程。
    """

    result = await knowledge_service.retry_document_version(
        owner_id=current_user.id,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
        document_version_id=document_version_id,
        components=components,
    )
    return DocumentVersionResponse(
        id=result.version.id,
        document_id=result.version.document_id,
        version_number=result.version.version_number,
        status=result.version.status,
        chunk_count=result.chunk_count,
        created_at=result.version.created_at,
    )


@router.post(
    "/{knowledge_base_id}/files",
    response_model=KnowledgeFileIngestionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid or missing access token.",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Knowledge base was not found.",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ErrorResponse,
            "description": "File content could not be parsed into knowledge chunks.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "Document version could not be prepared.",
        },
    },
)
async def upload_file_to_knowledge_base(
    knowledge_base_id: str,
    upload: Annotated[UploadFile, File(...)],
    current_user: Annotated[UserResponse, Depends(get_current_user)],
    knowledge_service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    components: Annotated[
        KnowledgeIndexingComponents,
        Depends(get_knowledge_indexing_components),
    ],
) -> KnowledgeFileIngestionResponse:
    """
    上传文件到一个 KnowledgeBase，并同步完成 Version 与 Chunk 的索引。

    调用方只选择目标知识库和上传文件；File、Document、Parser、Token、Chunk、
    Embedding Profile、processing_fingerprint 与 Qdrant 写入均由服务器按固定流程处理。
    索引失败时仍返回已保存的 File、Document 与失败 Version，客户端可据 Version 状态
    了解后续是否需要重试或清理，而不把已成功上传的文件错误显示为失败。
    """

    result = await knowledge_service.ingest_file_to_base(
        owner_id=current_user.id,
        knowledge_base_id=knowledge_base_id,
        original_filename=upload.filename,
        content_type=upload.content_type,
        source=upload.file,
        file_service=file_service,
        components=components,
    )
    return KnowledgeFileIngestionResponse(
        file=result.file_resource,
        document=KnowledgeDocumentResponse.model_validate(result.document),
        version=DocumentVersionResponse(
            id=result.version.id,
            document_id=result.version.document_id,
            version_number=result.version.version_number,
            status=result.version.status,
            chunk_count=len(result.chunks),
            created_at=result.version.created_at,
        ),
    )
