from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


def error_response(
    status_code: int, detail: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        {"status": status_code, "detail": detail}, status_code=status_code, headers=headers
    )


def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return error_response(exc.status_code, str(exc.detail), exc.headers)


def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Built from location and message only: pydantic's "input" field would echo passwords.
    messages = []
    for error in exc.errors():
        # For invalid JSON the location is a character offset, not a field.
        location = "" if error["type"] == "json_invalid" else ".".join(map(str, error["loc"][1:]))
        messages.append(f"{location}: {error['msg']}" if location else error["msg"])
    return error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(messages))


def unhandled_exception_handler(_: Request, __: Exception) -> JSONResponse:
    return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
