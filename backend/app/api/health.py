from fastapi import APIRouter, Response, status

from app.schemas.health import LivenessResponse, ReadinessResponse
from app.services.health_service import get_application_readiness

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("/live", response_model=LivenessResponse)
def liveness() -> LivenessResponse:
    return LivenessResponse(status="ok")


# response.status_code → 实际返回什么状态码
# return               → 实际返回什么数据
# response_model       → 默认响应验证 + Swagger
# responses            → 额外状态码的 Swagger 说明
@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessResponse,
            "description": "Application dependencies are unavailable.",
        },
    },
)
def readiness(response: Response) -> ReadinessResponse:
    readiness_status = get_application_readiness()
    if readiness_status.status == "not_ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return readiness_status
