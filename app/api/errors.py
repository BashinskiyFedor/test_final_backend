from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.errors import (
    ConflictError,
    DomainError,
    InvalidInputError,
    KeitaroError,
    NotFoundError,
)

_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    InvalidInputError: 422,
    KeitaroError: status.HTTP_502_BAD_GATEWAY,
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        code = next(
            (c for err, c in _STATUS_BY_ERROR.items() if isinstance(exc, err)),
            status.HTTP_400_BAD_REQUEST,
        )
        return JSONResponse({"detail": exc.message}, status_code=code)
