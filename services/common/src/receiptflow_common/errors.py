from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def not_found(what: str = "증빙") -> ApiError:
    return ApiError(404, "not_found", f"{what}을(를) 찾을 수 없습니다.")


def forbidden() -> ApiError:
    return ApiError(403, "forbidden", "접근 권한이 없습니다.")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        body = {"code": exc.code, "message": exc.message, **exc.extra}
        return JSONResponse({"error": body}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        body = {
            "code": "invalid_request",
            "message": "요청 형식이 올바르지 않습니다.",
            "details": exc.errors(),
        }
        return JSONResponse({"error": body}, status_code=400)
