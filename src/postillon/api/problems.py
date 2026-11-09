"""The error responses of the API, in RFC 9457 `application/problem+json`, and the checks of the
conditional requests (see docs/api.md).

Every error goes through here: the refusals of the service, the invalid requests and the HTTP
errors of the routing.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from postillon.errors import (
    Conflict,
    Gone,
    Invalid,
    NotFound,
    PreconditionFailed,
    Refused,
    UnsupportedMediaType,
    VideoTooLarge,
)

MEDIA_TYPE = "application/problem+json"
# The first class an error belongs to gives its status: the specific ones before their kind.
STATUSES: tuple[tuple[type[Refused], int], ...] = (
    (VideoTooLarge, status.HTTP_413_CONTENT_TOO_LARGE),
    (UnsupportedMediaType, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE),
    (NotFound, status.HTTP_404_NOT_FOUND),
    (Gone, status.HTTP_410_GONE),
    (Invalid, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (Conflict, status.HTTP_409_CONFLICT),
    (PreconditionFailed, status.HTTP_412_PRECONDITION_FAILED),
)
INVALID_REQUEST = "invalid-request"


def install(app: FastAPI) -> None:
    @app.exception_handler(Refused)
    async def refused(request: Request, error: Refused) -> JSONResponse:
        code = next(code for kind, code in STATUSES if isinstance(error, kind))
        return problem(code, error.code, str(error))

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, error: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in error.errors()]
        return problem(status.HTTP_422_UNPROCESSABLE_CONTENT, INVALID_REQUEST, "the request is invalid", errors=errors)

    @app.exception_handler(HTTPException)
    async def http(request: Request, error: HTTPException) -> JSONResponse:
        detail = error.detail if error.detail != HTTPStatus(error.status_code).phrase else None
        response = problem(error.status_code, "about:blank", detail)
        if error.headers:
            response.headers.update(error.headers)
        return response


def problem(code: int, type_: str, detail: str | None, **extensions: Any) -> JSONResponse:
    body: dict[str, Any] = {"type": type_, "title": HTTPStatus(code).phrase, "status": code}
    if detail:
        body["detail"] = detail
    return JSONResponse({**body, **extensions}, status_code=code, media_type=MEDIA_TYPE)


def check_preconditions(etag: str | None, if_match: str | None, if_none_match: str | None) -> None:
    """Raises PreconditionFailed when `If-Match` names none of the current representation (`etag`,
    None when the resource does not exist) or `If-None-Match` names it; RFC 9110, section 13."""
    if if_match is not None and (etag is None or not _matches(if_match, etag, weak=False)):
        raise PreconditionFailed("If-Match: the resource changed, or does not exist")
    if if_none_match is not None and etag is not None and _matches(if_none_match, etag, weak=True):
        raise PreconditionFailed("If-None-Match: the resource exists")


def not_modified(etag: str, if_none_match: str | None) -> bool:
    """Whether a read can answer 304: `If-None-Match` names the current representation."""
    return if_none_match is not None and _matches(if_none_match, etag, weak=True)


def _matches(header: str, etag: str, *, weak: bool) -> bool:
    tags = [tag.strip() for tag in header.split(",")]
    if "*" in tags:
        return True
    if weak:
        tags = [tag.removeprefix("W/") for tag in tags]
    return etag in tags
