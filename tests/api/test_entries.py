import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, update
from sqlalchemy.orm import Session, sessionmaker

from postillon.api.app import create_app
from postillon.db.models import Entry, Post
from postillon.domain import Status
from postillon.settings import Settings
from tests.support import MP4

ENTRIES = "/v1/projects/my-project/entries"
URL = f"{ENTRIES}/day-23"
VIDEO = f"{URL}/video"
MP4_ETAG = f'"{hashlib.sha256(MP4).hexdigest()}"'


@pytest.fixture
def client(settings: Settings, engine: Engine) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        yield client


def manifest(publish_at: str = "2099-10-22T18:00:00Z", tiktok: bool = False, **youtube: Any) -> dict[str, Any]:
    posts: dict[str, Any] = {"youtube": {"account": "main", "title": "Day 23", **youtube}}
    if tiktok:
        posts["tiktok"] = {"account": "main", "caption": "x"}
    return {"publish_at": publish_at, "posts": posts}


def put_video(client: TestClient, content: bytes = MP4, url: str = VIDEO, **headers: str) -> Any:
    return client.put(url, content=content, headers={"content-type": "video/mp4", **headers})


def problem(response: Any) -> tuple[int, str]:
    assert response.headers["content-type"] == "application/problem+json"
    return response.status_code, response.json()["type"]


def set_status(session_factory: sessionmaker[Session], platform: str, status: Status) -> None:
    with session_factory() as session:
        session.execute(update(Post).where(Post.platform == platform).values(status=status, version=Post.version + 1))
        session.commit()


# The entry


def test_put_creates_then_replaces_the_entry(client: TestClient):
    created = client.put(URL, json=manifest())
    assert (created.status_code, created.headers["location"]) == (201, URL)
    body = created.json()
    assert (body["key"], body["video"], body["posts"][0]["status"]) == ("day-23", None, "pending")
    replaced = client.put(URL, json=manifest(title="Day 23 bis"))
    assert replaced.status_code == 200
    assert replaced.json()["manifest"]["posts"]["youtube"]["title"] == "Day 23 bis"
    assert replaced.headers["etag"] != created.headers["etag"]


def test_invalid_manifest_names_its_faulty_fields(client: TestClient):
    response = client.put(URL, json={"publish_at": "2099-10-22T18:00:00", "posts": {"youtube": {"account": "main"}}})
    assert problem(response) == (422, "invalid-request")
    assert [e["loc"] for e in response.json()["errors"]] == [
        ["body", "publish_at"],
        ["body", "posts", "youtube", "title"],
    ]


@pytest.mark.parametrize(
    ("url", "body", "expected"),
    [
        ("/v1/projects/other/entries/day", manifest(), (404, "project-not-found")),
        (URL, manifest(account="other"), (422, "account-not-configured")),
        ("/v1/projects/My-Project/entries/day", manifest(), (422, "invalid-request")),
        (f"{ENTRIES}/Day-23", manifest(), (422, "invalid-request")),
    ],
)
def test_refused_entries(client: TestClient, url: str, body: dict[str, Any], expected: tuple[int, str]):
    assert problem(client.put(url, json=body)) == expected


def test_entry_is_json_only(client: TestClient):
    assert problem(client.put(URL, data={"entry": "{}"})) == (415, "unsupported-media-type")


def test_conditional_put(client: TestClient):
    created = client.put(URL, json=manifest(), headers={"If-None-Match": "*"})
    assert created.status_code == 201
    assert problem(client.put(URL, json=manifest(), headers={"If-None-Match": "*"})) == (412, "precondition-failed")
    etag = created.headers["etag"]
    assert client.put(URL, json=manifest(title="b"), headers={"If-Match": etag}).status_code == 200
    assert problem(client.put(URL, json=manifest(title="c"), headers={"If-Match": etag})) == (
        412,
        "precondition-failed",
    )


def test_entry_is_read_with_its_etag(client: TestClient, session_factory):
    client.put(URL, json=manifest())
    response = client.get(URL)
    etag = response.headers["etag"]
    assert response.json()["posts"][0]["outdated"] is False
    assert client.get(URL, headers={"If-None-Match": etag}).status_code == 304
    set_status(session_factory, "youtube", Status.SCHEDULED)
    assert client.get(URL, headers={"If-None-Match": etag}).status_code == 200
    assert problem(client.get(f"{ENTRIES}/unknown")) == (404, "entry-not-found")


def test_a_sent_post_is_outdated_by_a_new_manifest(client: TestClient, session_factory):
    client.put(URL, json=manifest())
    set_status(session_factory, "youtube", Status.SCHEDULED)
    post = client.put(URL, json=manifest("2099-10-23T18:00:00Z")).json()["posts"][0]
    assert (post["publish_at"], post["outdated"]) == ("2099-10-22T18:00:00Z", True)
    assert client.put(URL, json=manifest()).json()["posts"][0]["outdated"] is False


# The video


def test_video_is_put_then_served(client: TestClient):
    client.put(URL, json=manifest())
    created = put_video(client)
    assert (created.status_code, created.headers["etag"], created.headers["location"]) == (201, MP4_ETAG, VIDEO)
    assert put_video(client).status_code == 204
    response = client.get(VIDEO)
    assert (response.status_code, response.content, response.headers["etag"]) == (200, MP4, MP4_ETAG)
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["content-disposition"] == 'inline; filename="my-project-day-23.mp4"'
    assert client.get(VIDEO, headers={"Range": "bytes=0-9"}).content == MP4[:10]
    assert client.head(VIDEO).status_code == 200
    assert client.get(URL).json()["video"]["sha256"] == MP4_ETAG.strip('"')


def test_a_new_video_replaces_the_file(client: TestClient, settings: Settings):
    client.put(URL, json=manifest())
    put_video(client)
    assert put_video(client, MP4 + b"new").status_code == 204
    assert client.get(VIDEO).content == MP4 + b"new"
    assert len(list((settings.videos_dir / "my-project").glob("day-23.*.mp4"))) == 1


@pytest.mark.parametrize(
    ("content", "headers", "expected"),
    [
        (b"not a video", {}, (415, "video-not-mp4")),
        (MP4 + b"\x00" * 10_000, {}, (413, "video-too-large")),
        (MP4, {"content-type": "application/octet-stream"}, (415, "unsupported-media-type")),
        (MP4, {"If-Match": '"other"'}, (412, "precondition-failed")),
    ],
)
def test_refused_videos_leave_no_file(
    client: TestClient, settings: Settings, content: bytes, headers: dict[str, str], expected: tuple[int, str]
):
    client.put(URL, json=manifest())
    assert problem(put_video(client, content, **headers)) == expected
    assert list(settings.videos_dir.rglob("*.mp4")) == []


def test_video_of_an_unknown_entry_is_refused(client: TestClient):
    assert problem(put_video(client)) == (404, "entry-not-found")


def test_video_states(client: TestClient, session_factory):
    client.put(URL, json=manifest())
    assert problem(client.get(VIDEO)) == (404, "video-not-found")
    put_video(client)
    with session_factory() as session:
        session.execute(update(Entry).values(video_released_at=datetime.now(UTC), version=Entry.version + 1))
        session.commit()
    assert problem(client.get(VIDEO)) == (410, "video-released")
    assert put_video(client).status_code == 201


# The posts and their history


def put_tiktok(client: TestClient, publish_at: str = "2099-10-22T18:00:00Z") -> None:
    client.put(URL, json=manifest(publish_at, tiktok=True))
    put_video(client)


def test_manual_post_is_marked_scheduled(client: TestClient):
    put_tiktok(client)
    etag = client.get(f"{URL}/posts/tiktok").headers["etag"]
    response = client.post(f"{URL}/posts/tiktok:mark-scheduled", headers={"If-Match": etag})
    assert response.status_code == 200
    assert (response.json()["status"], response.json()["manual"]) == ("scheduled", True)
    assert client.get(f"{URL}/posts/youtube").json()["manual"] is False
    events = client.get(f"{URL}/posts/tiktok/events").json()
    assert [e["status"] for e in events["events"]] == ["pending", "scheduled"]
    assert events["next_page_token"] is None


@pytest.mark.parametrize(
    ("publish_at", "platform", "expected"),
    [
        ("2099-10-22T18:00:00Z", "instagram", (404, "post-not-found")),
        ("2099-10-22T18:00:00Z", "youtube", (422, "platform-not-manual")),
        ("2000-10-22T18:00:00Z", "tiktok", (409, "publish-at-passed")),
    ],
)
def test_refused_scheduling(client: TestClient, publish_at: str, platform: str, expected: tuple[int, str]):
    put_tiktok(client, publish_at)
    assert problem(client.post(f"{URL}/posts/{platform}:mark-scheduled")) == expected


def test_a_post_without_video_cannot_be_scheduled(client: TestClient):
    client.put(URL, json=manifest(tiktok=True))
    assert problem(client.post(f"{URL}/posts/tiktok:mark-scheduled")) == (409, "video-not-held")


def test_a_post_scheduled_twice_is_refused(client: TestClient):
    put_tiktok(client)
    client.post(f"{URL}/posts/tiktok:mark-scheduled")
    assert problem(client.post(f"{URL}/posts/tiktok:mark-scheduled")) == (409, "transition-refused")
    assert client.get(f"{URL}/posts/tiktok:mark-scheduled").status_code == 405


def test_events_of_every_post_are_paged(client: TestClient):
    put_tiktok(client)
    client.post(f"{URL}/posts/tiktok:mark-scheduled")
    first = client.get(f"{URL}/posts/-/events", params={"page_size": 2}).json()
    assert [(e["platform"], e["status"]) for e in first["events"]] == [("youtube", "pending"), ("tiktok", "pending")]
    rest = client.get(f"{URL}/posts/-/events", params={"page_size": 2, "page_token": first["next_page_token"]}).json()
    assert [(e["platform"], e["status"]) for e in rest["events"]] == [("tiktok", "scheduled")]
    assert rest["next_page_token"] is None
    other = client.get(f"{URL}/posts/tiktok/events", params={"page_token": first["next_page_token"]})
    assert problem(other) == (422, "invalid-page-token")


# The list


def test_entries_are_listed_paged_and_filtered(client: TestClient, session_factory):
    for day, publish_at in ((23, "2099-10-23T18:00:00Z"), (24, "2099-10-24T18:00:00Z"), (25, "2099-10-25T18:00:00Z")):
        client.put(f"{ENTRIES}/day-{day}", json=manifest(publish_at, tiktok=day == 24))

    def keys(project: str = "my-project", **params: Any) -> list[str]:
        response = client.get(f"/v1/projects/{project}/entries", params=params)
        assert response.status_code == 200, response.json()
        return [e["key"] for e in response.json()["entries"]]

    assert keys() == ["day-25", "day-24", "day-23"]
    assert keys("-", order_by="publish_at") == ["day-23", "day-24", "day-25"]
    assert keys(filter='posts.manual = true AND posts.status = "pending"') == ["day-24"]
    assert keys(filter='publish_at >= "2099-10-24T00:00:00Z" AND posts.platform = "youtube"') == ["day-25", "day-24"]
    set_status(session_factory, "tiktok", Status.SCHEDULED)
    assert keys(filter='posts.manual = true AND posts.status = "pending"') == []
    first = client.get(f"{ENTRIES}", params={"page_size": 2}).json()
    rest = client.get(f"{ENTRIES}", params={"page_size": 2, "page_token": first["next_page_token"]}).json()
    assert [e["key"] for e in first["entries"] + rest["entries"]] == ["day-25", "day-24", "day-23"]
    assert rest["next_page_token"] is None
    moved = client.get(f"{ENTRIES}", params={"page_token": first["next_page_token"], "order_by": "publish_at"})
    assert problem(moved) == (422, "invalid-page-token")


@pytest.mark.parametrize(
    ("project", "params", "expected"),
    [
        ("other", {}, (404, "project-not-found")),
        ("my-project", {"filter": 'posts.colour = "red"'}, (422, "invalid-filter")),
        ("my-project", {"filter": 'posts.status = "lost"'}, (422, "invalid-filter")),
        ("my-project", {"filter": 'publish_at > "tomorrow"'}, (422, "invalid-filter")),
        ("my-project", {"filter": 'posts.status != "pending"'}, (422, "invalid-filter")),
        ("my-project", {"order_by": "key"}, (422, "invalid-order-by")),
        ("my-project", {"page_token": "garbage"}, (422, "invalid-page-token")),
        ("my-project", {"page_size": 501}, (422, "invalid-request")),
    ],
)
def test_refused_lists(client: TestClient, project: str, params: dict[str, Any], expected: tuple[int, str]):
    assert problem(client.get(f"/v1/projects/{project}/entries", params=params)) == expected


# Entries published outside the service


def record_body(key: str = "day-2", **published: Any) -> dict[str, Any]:
    return {
        "key": key,
        "manifest": {
            "publish_at": "2026-10-12T18:00:00Z",
            "posts": {"youtube": {"account": "main", "title": "Day 2"}, "tiktok": {"account": "main", "caption": "x"}},
        },
        "published": published
        or {
            "youtube": {"at": "2026-10-12T18:00:00Z", "remote_id": "abc"},
            "tiktok": {"at": "2026-10-12T21:30:00+02:00"},
        },
    }


def test_entry_published_outside_is_recorded(client: TestClient):
    response = client.post(f"{ENTRIES}:record", json=record_body())
    assert (response.status_code, response.headers["location"]) == (201, f"{ENTRIES}/day-2")
    body = response.json()
    assert body["video"] is None
    posts = {p["platform"]: p for p in body["posts"]}
    assert (posts["youtube"]["status"], posts["youtube"]["remote_id"]) == ("published", "abc")
    assert [p["outdated"] for p in body["posts"]] == [False, False]
    events = client.get(f"{ENTRIES}/day-2/posts/tiktok/events").json()["events"]
    assert [(e["status"], e["at"]) for e in events] == [("published", "2026-10-12T19:30:00Z")]
    assert problem(client.get(f"{ENTRIES}/day-2/video")) == (404, "video-not-found")


@pytest.mark.parametrize(
    ("url", "body", "expected"),
    [
        ("/v1/projects/unknown/entries:record", record_body(), (404, "project-not-found")),
        (f"{ENTRIES}:record", record_body(youtube={"at": "2026-10-12T18:00:00Z"}), (422, "publications-mismatch")),
        (
            f"{ENTRIES}:record",
            record_body(youtube={"at": "2026-10-12T18:00:00Z"}, tiktok={"at": "2099-10-12T18:00:00Z"}),
            (422, "publication-in-future"),
        ),
        (f"{ENTRIES}:record", record_body("Day-2"), (422, "invalid-request")),
    ],
)
def test_refused_records(client: TestClient, url: str, body: dict[str, Any], expected: tuple[int, str]):
    assert problem(client.post(url, json=body)) == expected


def test_record_never_changes_an_entry(client: TestClient):
    client.put(f"{ENTRIES}/day-2", json=manifest())
    assert problem(client.post(f"{ENTRIES}:record", json=record_body())) == (409, "entry-exists")
    assert client.get(f"{ENTRIES}/day-2").json()["posts"][0]["status"] == "pending"


# Outside the contract


def test_health(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}


def test_unknown_routes_answer_a_problem(client: TestClient):
    assert problem(client.get("/v1/unknown")) == (404, "about:blank")
    assert problem(client.delete(URL)) == (405, "about:blank")


def test_admin_page_is_served_under_its_prefix(client: TestClient):
    assert client.get("/", follow_redirects=False).headers["location"] == "/admin/"
    page = client.get("/admin/")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert '<script type="module" src="schedule.js">' in page.text
    for asset in ("publications.html", "entry.html", "common.js", "style.css", "fonts/barlow-condensed-600.woff2"):
        assert client.get(f"/admin/{asset}").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/admin/missing.js").status_code == 404


def test_app_refuses_a_database_not_migrated(settings: Settings):
    with pytest.raises(ValueError, match="run `postillon migrate`"):
        create_app(settings)
