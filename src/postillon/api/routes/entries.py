"""The routes of the entries, their video, their posts and the posts' history (see docs/api.md).

Each route reads, calls one service, commits and answers the resource it acted on; the refusals go
to `postillon.api.problems`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, sessionmaker
from starlette.convertors import Convertor, register_url_convertor

from postillon.api import listing
from postillon.api.deps import SessionDep, SessionsDep, SettingsDep, VideosDep
from postillon.api.problems import check_preconditions, not_modified
from postillon.api.representations import (
    EntryList,
    EntryOut,
    EventList,
    PostOut,
    RecordIn,
    entry_etag,
    entry_out,
    event_out,
    post_etag,
    post_out,
    video_etag,
)
from postillon.db.models import Entry, Post
from postillon.errors import (
    EntryNotFound,
    PostNotFound,
    ProjectNotFound,
    UnsupportedMediaType,
    VideoNotFound,
    VideoReleased,
    VideoTooLarge,
)
from postillon.manifest import Manifest
from postillon.services import entries, reception, recording
from postillon.services.recording import Publication
from postillon.services.scheduling import mark_scheduled
from postillon.services.submission import submit
from postillon.services.transaction import commit
from postillon.storage.videos import Staged, VideoStore

# Stands for every project in a list, and every post in a history (AIP-159).
WILDCARD = "-"
PAGE_SIZE = 100
MAX_PAGE_SIZE = 500
BINARY = {"type": "string", "format": "binary"}
# The body is written and hashed in the thread pool, a mebibyte at a time, off the event loop.
WRITE_BYTES = 1024 * 1024


class Segment(Convertor[str]):
    """One path segment without `:`, which separates a resource from its custom method (AIP-136)."""

    regex = "[^/:]+"

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return value


register_url_convertor("segment", Segment())

router = APIRouter(tags=["entries"])

ProjectPath = Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9-]*$")]
ProjectsPath = Annotated[str, Path(pattern=r"^(-|[a-z0-9][a-z0-9-]*)$", description="A project, or `-` for all.")]
KeyPath = Annotated[str, Path(pattern=r"^[a-z0-9_-]+$", max_length=200)]
PlatformPath = Annotated[str, Path(pattern=r"^[a-z0-9_-]+$")]
PostsPath = Annotated[str, Path(pattern=r"^[a-z0-9_-]+$", description="A platform, or `-` for all the posts.")]
PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
IfMatch = Annotated[str | None, Header()]
IfNoneMatch = Annotated[str | None, Header()]

ENTRY = "/projects/{project:segment}/entries/{key:segment}"
POST = ENTRY + "/posts/{platform:segment}"


def _media_type(request: Request) -> str:
    return request.headers.get("content-type", "").split(";")[0].strip().lower()


def _json_body(request: Request) -> None:
    if _media_type(request) != "application/json":
        raise UnsupportedMediaType("the body is JSON, sent as application/json")


JsonBody = Depends(_json_body)


@router.get("/projects/{project:segment}/entries")
def list_entries(
    project: ProjectsPath,
    session: SessionDep,
    settings: SettingsDep,
    filter_: Annotated[str, Query(alias="filter", description="AIP-160 subset, see docs/api.md.")] = "",
    order_by: Annotated[str, Query(description="`publish_at` or `publish_at desc`, the default.")] = "",
    page_size: PageSize = PAGE_SIZE,
    page_token: str = "",
) -> EntryList:
    """The entries of a project, or of all projects, a page at a time."""
    scope = None if project == WILDCARD else project
    if scope is not None and scope not in settings.projects:
        raise ProjectNotFound(f"project {project!r} is not configured")
    query = listing.entry_query(scope, filter_, order_by, page_token, page_size + 1)
    found = entries.find(session, query)
    page = list(found[:page_size])
    token = None
    if len(found) > page_size:
        last = page[-1]
        token = listing.entry_token(scope, filter_, order_by, last.publish_at, last.id)
    return EntryList(entries=[entry_out(entry) for entry in page], next_page_token=token)


@router.put(
    ENTRY,
    dependencies=[JsonBody],
    responses={201: {"model": EntryOut}, 404: {}, 409: {}, 412: {}, 415: {}, 422: {}},
)
def put_entry(
    project: ProjectPath,
    key: KeyPath,
    manifest: Manifest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    if_match: IfMatch = None,
    if_none_match: IfNoneMatch = None,
) -> EntryOut:
    """Creates or replaces an entry from its manifest. A post that may have reached its platform keeps
    what it was sent with, and says so by `outdated`."""
    current = entries.get(session, project, key)
    check_preconditions(entry_etag(current) if current else None, if_match, if_none_match)
    submitted = submit(session, settings, project=project, key=key, manifest=manifest, now=datetime.now(UTC))
    commit(session)
    if submitted.created:
        response.status_code = status.HTTP_201_CREATED
        response.headers["Location"] = request.url.path
    response.headers["ETag"] = entry_etag(submitted.entry)
    return entry_out(submitted.entry)


@router.get(ENTRY, response_model=EntryOut, responses={304: {}, 404: {}})
def get_entry(
    project: ProjectPath, key: KeyPath, session: SessionDep, response: Response, if_none_match: IfNoneMatch = None
) -> Any:
    """The entry, the state of its posts and of its video."""
    entry = entries.get(session, project, key)
    if entry is None:
        raise EntryNotFound(f"entry {project}/{key} does not exist")
    etag = entry_etag(entry)
    if not_modified(etag, if_none_match):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return entry_out(entry)


@router.post(
    "/projects/{project:segment}/entries:record",
    status_code=status.HTTP_201_CREATED,
    dependencies=[JsonBody],
    responses={404: {}, 409: {}, 415: {}, 422: {}},
)
def record_entry(
    project: ProjectPath,
    body: RecordIn,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> EntryOut:
    """Creates an entry published outside the service, each post `published` at its time. Never
    changes an existing entry."""
    published = {name: Publication(at=p.at, remote_id=p.remote_id) for name, p in body.published.items()}
    entry = recording.record(
        session,
        settings,
        project=project,
        key=body.key,
        manifest=body.manifest,
        published=published,
        now=datetime.now(UTC),
    )
    commit(session)
    response.headers["Location"] = request.url_for("get_entry", project=project, key=body.key).path
    response.headers["ETag"] = entry_etag(entry)
    return entry_out(entry)


@router.put(
    ENTRY + "/video",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={201: {}, 404: {}, 409: {}, 412: {}, 413: {}, 415: {}},
    openapi_extra={
        "requestBody": {"required": True, "content": {"video/mp4": {"schema": {"type": "string", "format": "binary"}}}}
    },
)
async def put_video(
    project: ProjectPath,
    key: KeyPath,
    request: Request,
    sessions: SessionsDep,
    videos: VideosDep,
    content_length: Annotated[int | None, Header()] = None,
    if_match: IfMatch = None,
    if_none_match: IfNoneMatch = None,
) -> Response:
    """Sets the video of the entry, an MP4 file sent as the body: `201` for a first video, `204` for
    a replacement; the posts not sent yet take it."""
    if _media_type(request) != "video/mp4":
        raise UnsupportedMediaType("the body is the video, sent as video/mp4")
    if content_length is not None and content_length > videos.max_bytes:
        raise VideoTooLarge(f"video is over {videos.max_bytes} bytes")
    await run_in_threadpool(_check_video, sessions, project, key, if_match, if_none_match)
    with videos.upload() as upload:
        buffer = bytearray()
        async for chunk in request.stream():
            buffer += chunk
            if len(buffer) >= WRITE_BYTES:
                await run_in_threadpool(upload.write, bytes(buffer))
                buffer.clear()
        await run_in_threadpool(upload.write, bytes(buffer))
        staged = await run_in_threadpool(upload.finish)
    try:
        created = await run_in_threadpool(_store_video, sessions, videos, project, key, staged, if_match, if_none_match)
    finally:
        videos.discard(staged)
    headers = {"ETag": video_etag(staged.sha256)}
    if created:
        return Response(status_code=status.HTTP_201_CREATED, headers={**headers, "Location": request.url.path})
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)


@router.get(
    ENTRY + "/video",
    response_class=FileResponse,
    responses={200: {"content": {"video/mp4": {}}}, 304: {}, 404: {}, 410: {}},
)
def get_video(
    project: ProjectPath, key: KeyPath, session: SessionDep, videos: VideosDep, if_none_match: IfNoneMatch = None
) -> Response:
    """The video of the entry, while the service holds it."""
    entry = _entry(session, project, key)
    if entry.video_sha256 is None:
        raise VideoNotFound(f"entry {project}/{key} has no video")
    if entry.video_released_at is not None:
        raise VideoReleased(f"every platform holds the video, released {entry.video_released_at.isoformat()}")
    etag = video_etag(entry.video_sha256)
    if not_modified(etag, if_none_match):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    return FileResponse(
        videos.path(project, key, entry.video_sha256),
        media_type="video/mp4",
        filename=f"{project}-{key}.mp4",
        content_disposition_type="inline",
        headers={"ETag": etag},
    )


# The `<video>` element of the administration page sends HEAD before its range requests.
router.add_api_route(
    ENTRY + "/video", get_video, methods=["HEAD"], response_class=FileResponse, include_in_schema=False
)


@router.get(POST, response_model=PostOut, responses={304: {}, 404: {}})
def get_post(
    project: ProjectPath,
    key: KeyPath,
    platform: PlatformPath,
    session: SessionDep,
    response: Response,
    if_none_match: IfNoneMatch = None,
) -> Any:
    """One post of the entry."""
    post = _post(session, project, key, platform)
    etag = post_etag(post)
    if not_modified(etag, if_none_match):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return post_out(post, post.entry)


@router.post(POST + ":mark-scheduled", responses={404: {}, 409: {}, 412: {}, 422: {}})
def mark_post_scheduled(
    project: ProjectPath,
    key: KeyPath,
    platform: PlatformPath,
    session: SessionDep,
    response: Response,
    if_match: IfMatch = None,
) -> PostOut:
    """Records that the operator scheduled the post on its platform, which publishes it at `publish_at`.
    Only for a pending post of a manual platform, before its publication time."""
    check_preconditions(post_etag(_post(session, project, key, platform)), if_match, None)
    post = mark_scheduled(session, project=project, key=key, platform=platform, now=datetime.now(UTC))
    commit(session)
    response.headers["ETag"] = post_etag(post)
    return post_out(post, post.entry)


@router.get(POST + "/events", responses={404: {}})
def list_events(
    project: ProjectPath,
    key: KeyPath,
    platform: PostsPath,
    session: SessionDep,
    page_size: PageSize = PAGE_SIZE,
    page_token: str = "",
) -> EventList:
    """The statuses a post took, or all the posts of the entry with `-`, in the order recorded."""
    _entry(session, project, key)
    if platform != WILDCARD:
        _post(session, project, key, platform)
    scope = {"project": project, "key": key, "platform": platform}
    after = listing.event_after(scope, page_token)
    found = entries.events(
        session, project, key, platform=None if platform == WILDCARD else platform, after=after, limit=page_size + 1
    )
    page = list(found[:page_size])
    token = listing.event_token(scope, page[-1].id) if len(found) > page_size else None
    return EventList(events=[event_out(event) for event in page], next_page_token=token)


def _entry(session: Session, project: str, key: str) -> Entry:
    entry = entries.get(session, project, key)
    if entry is None:
        raise EntryNotFound(f"entry {project}/{key} does not exist")
    return entry


def _post(session: Session, project: str, key: str, platform: str) -> Post:
    post = entries.get_post(session, project, key, platform)
    if post is None:
        raise PostNotFound(f"entry {project}/{key} has no {platform} post")
    return post


def _held_etag(entry: Entry) -> str | None:
    return video_etag(entry.video_sha256) if entry.holds_video and entry.video_sha256 else None


def _check_video(
    sessions: sessionmaker[Session], project: str, key: str, if_match: str | None, if_none_match: str | None
) -> None:
    """Refuses a video before its bytes are read: unknown entry, or a precondition already failing."""
    with sessions() as session:
        check_preconditions(_held_etag(_entry(session, project, key)), if_match, if_none_match)


def _store_video(
    sessions: sessionmaker[Session],
    videos: VideoStore,
    project: str,
    key: str,
    staged: Staged,
    if_match: str | None,
    if_none_match: str | None,
) -> bool:
    """Records the staged video as the entry's and moves it into place; whether it creates the video."""
    with sessions() as session:
        entry = _entry(session, project, key)
        check_preconditions(_held_etag(entry), if_match, if_none_match)
        created = not entry.holds_video
        received = reception.receive(entry, staged, datetime.now(UTC))
        if not received.changed:
            return False
        commit(session)
    videos.promote(staged, project, key)
    if received.replaced is not None and received.replaced != staged.sha256:
        videos.delete(project, key, received.replaced)
    return created
