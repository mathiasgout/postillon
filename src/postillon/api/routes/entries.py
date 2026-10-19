"""The routes of the entries: submit one, read one and its video, list them, mark a manual post
scheduled (see docs/api.md)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Path, Query, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from pydantic import ValidationError

from postillon.api.deps import SessionDep, SettingsDep, VideosDep
from postillon.api.schemas import EntryOut, SubmissionOut
from postillon.domain import Status
from postillon.manifest import Manifest
from postillon.services import entries
from postillon.services.scheduling import NotManual, PostNotFound, SchedulingConflict, mark_scheduled
from postillon.services.submission import SubmissionConflict, SubmissionRefused, UnknownProject, submit

router = APIRouter(tags=["entries"])

ProjectPath = Annotated[str, Path(pattern=r"^[a-z0-9-]+$")]
KeyPath = Annotated[str, Path(pattern=r"^[a-z0-9_-]+(/[a-z0-9_-]+)*$", max_length=200)]
PlatformPath = Annotated[str, Path(pattern=r"^[a-z0-9_-]+$")]


@router.put(
    "/projects/{project}/entries/{key:path}",
    responses={201: {"model": SubmissionOut}, 404: {}, 409: {}, 422: {}},
)
def put_entry(
    project: ProjectPath,
    key: KeyPath,
    session: SessionDep,
    settings: SettingsDep,
    videos: VideosDep,
    response: Response,
    entry: Annotated[str, Form(description="The manifest of the entry, as JSON.")],
    video: Annotated[
        UploadFile | None, File(description="The MP4 video; optional while the service holds one.")
    ] = None,
) -> SubmissionOut:
    """Creates or replaces an entry. A post that may have reached its platform is left as it was
    sent and listed in `ignored`."""
    try:
        manifest = Manifest.model_validate_json(entry)
    except ValidationError as e:
        raise RequestValidationError(
            [
                {**error, "loc": ("body", "entry", *error["loc"])}
                for error in e.errors(include_url=False, include_context=False)
            ],
        ) from None
    try:
        submitted = submit(
            session,
            settings,
            videos,
            project=project,
            key=key,
            manifest=manifest,
            video=video.file if video else None,
            now=datetime.now(UTC),
        )
    except UnknownProject as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None
    except SubmissionRefused as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    except SubmissionConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    if submitted.created:
        response.status_code = status.HTTP_201_CREATED
    entry_out = EntryOut.model_validate(entries.get(session, project, key))
    return SubmissionOut(entry=entry_out, ignored=submitted.ignored)


# Declared before `get_entry`, whose `{key:path}` would take the suffix; a key never holds a dot.
@router.get(
    "/projects/{project}/entries/{key:path}.mp4",
    response_class=FileResponse,
    responses={200: {"content": {"video/mp4": {}}}, 404: {}},
)
def get_video(project: ProjectPath, key: KeyPath, videos: VideosDep) -> FileResponse:
    """The video of the entry, while the service holds it."""
    path = videos.path(project, key)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"the service holds no video of {project}/{key}")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"{project}-{key.replace('/', '-')}.mp4",
        content_disposition_type="inline",
    )


@router.get("/projects/{project}/entries/{key:path}", responses={404: {}})
def get_entry(project: ProjectPath, key: KeyPath, session: SessionDep) -> EntryOut:
    """The entry, the state of its posts and the history of their statuses."""
    found = entries.get(session, project, key)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"entry {project}/{key} does not exist")
    return EntryOut.model_validate(found)


@router.get("/entries")
def list_entries(
    session: SessionDep,
    project: str | None = None,
    post_status: Annotated[Status | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EntryOut]:
    """The entries, latest publication first, of one project or all, with a post of one status or any."""
    return [EntryOut.model_validate(e) for e in entries.find(session, project, post_status, limit, offset)]


@router.post("/projects/{project}/entries/{key:path}/posts/{platform}/scheduled", responses={404: {}, 409: {}, 422: {}})
def schedule_post(project: ProjectPath, key: KeyPath, platform: PlatformPath, session: SessionDep) -> EntryOut:
    """Records that the operator scheduled the post on its platform, which publishes it at `publish_at`.
    Only for a pending post of a manual platform, before its publication time."""
    try:
        mark_scheduled(session, project=project, key=key, platform=platform, now=datetime.now(UTC))
    except PostNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None
    except NotManual as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    except SchedulingConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return EntryOut.model_validate(entries.get(session, project, key))
