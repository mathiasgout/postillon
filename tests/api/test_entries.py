import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from postillon.api.app import create_app
from postillon.settings import Settings
from tests.support import MP4

URL = "/v1/projects/my-project/entries/season-1/day-23"


@pytest.fixture
def client(settings: Settings, engine: Engine) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        yield client


def manifest(**youtube: Any) -> str:
    return json.dumps(
        {"publish_at": "2026-10-22T18:00:00Z", "posts": {"youtube": {"account": "main", "title": "Day 23", **youtube}}}
    )


def put(client: TestClient, entry: str, video: bytes | None = MP4, url: str = URL) -> Any:
    files = {"video": ("day-23.mp4", video, "video/mp4")} if video is not None else None
    return client.put(url, data={"entry": entry}, files=files)


def test_submission_creates_then_replaces_the_entry(client: TestClient):
    created = put(client, manifest())
    assert created.status_code == 201
    body = created.json()
    assert body["ignored"] == []
    assert body["entry"]["key"] == "season-1/day-23"
    assert body["entry"]["posts"][0]["status"] == "pending"
    replaced = put(client, manifest(title="Day 23 bis"), video=None)
    assert replaced.status_code == 200
    assert replaced.json()["entry"]["manifest"]["posts"]["youtube"]["title"] == "Day 23 bis"


def test_invalid_manifest_names_its_faulty_fields(client: TestClient):
    response = put(client, json.dumps({"publish_at": "2026-10-22T18:00:00", "posts": {"youtube": {"account": "main"}}}))
    assert response.status_code == 422
    assert [e["loc"] for e in response.json()["detail"]] == [
        ["body", "entry", "publish_at"],
        ["body", "entry", "posts", "youtube", "title"],
    ]


@pytest.mark.parametrize(
    ("url", "entry", "video", "status", "detail"),
    [
        ("/v1/projects/other/entries/day", manifest(), MP4, 404, "project 'other' is not configured"),
        (URL, manifest(account="other"), MP4, 422, "account 'other' is not configured for youtube in my-project"),
        (URL, manifest(), None, 422, "video is missing"),
        (URL, manifest(), b"not a video", 422, "video is not an MP4 file"),
    ],
)
def test_refused_submissions(client: TestClient, url: str, entry: str, video: bytes | None, status: int, detail: str):
    response = put(client, entry, video=video, url=url)
    assert (response.status_code, response.json()["detail"]) == (status, detail)


@pytest.mark.parametrize("url", ["/v1/projects/My-Project/entries/day", "/v1/projects/my-project/entries/Day 23"])
def test_malformed_names_are_refused(client: TestClient, url: str):
    assert put(client, manifest(), url=url).status_code == 422


def test_entry_is_read_with_its_history(client: TestClient):
    put(client, manifest())
    response = client.get(URL)
    assert response.status_code == 200
    events = response.json()["posts"][0]["events"]
    assert [e["status"] for e in events] == ["pending"]
    assert client.get("/v1/projects/my-project/entries/unknown").status_code == 404


def test_entries_are_listed_and_filtered(client: TestClient):
    put(client, manifest())
    put(client, manifest(), url="/v1/projects/my-project/entries/season-1/day-24")
    keys = [e["key"] for e in client.get("/v1/entries").json()]
    assert sorted(keys) == ["season-1/day-23", "season-1/day-24"]
    assert len(client.get("/v1/entries", params={"status": "pending", "limit": 1}).json()) == 1
    assert client.get("/v1/entries", params={"status": "published"}).json() == []
    assert client.get("/v1/entries", params={"project": "other"}).json() == []
    assert client.get("/v1/entries", params={"status": "unknown"}).status_code == 422


def test_health(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}


def test_admin_page_is_served_beside_the_routes(client: TestClient):
    page = client.get("/")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert '<script src="app.js">' in page.text
    for asset in ("/app.js", "/style.css"):
        assert client.get(asset).status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/v1/entries").json() == []
    assert client.get("/missing.js").status_code == 404


def test_app_refuses_a_database_not_migrated(settings: Settings):
    with pytest.raises(ValueError, match="run `postillon migrate`"):
        create_app(settings)


def tiktok_manifest(publish_at: str = "2099-10-22T18:00:00Z") -> str:
    return json.dumps(
        {
            "publish_at": publish_at,
            "posts": {"youtube": {"account": "main", "title": "Day 23"}, "tiktok": {"account": "main", "caption": "x"}},
        }
    )


def test_video_is_served_while_the_service_holds_it(client: TestClient, settings: Settings):
    put(client, manifest())
    response = client.get(f"{URL}.mp4")
    assert (response.status_code, response.content) == (200, MP4)
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["content-disposition"] == 'inline; filename="my-project-season-1-day-23.mp4"'
    (settings.videos_dir / "my-project" / "season-1" / "day-23.mp4").unlink()
    assert client.get(f"{URL}.mp4").status_code == 404
    assert client.get(URL).status_code == 200


def test_manual_post_is_marked_scheduled(client: TestClient):
    put(client, tiktok_manifest())
    response = client.post(f"{URL}/posts/tiktok/scheduled")
    assert response.status_code == 200
    posts = {p["platform"]: p for p in response.json()["posts"]}
    assert posts["tiktok"]["status"] == "scheduled"
    assert [e["status"] for e in posts["tiktok"]["events"]] == ["pending", "scheduled"]
    assert posts["youtube"]["status"] == "pending"
    assert (posts["tiktok"]["manual"], posts["youtube"]["manual"]) == (True, False)


@pytest.mark.parametrize(
    ("publish_at", "path", "status", "detail"),
    [
        ("2099-10-22T18:00:00Z", "/posts/instagram/scheduled", 404, "has no instagram post"),
        ("2099-10-22T18:00:00Z", "/posts/youtube/scheduled", 422, "youtube is published by the service"),
        ("2000-10-22T18:00:00Z", "/posts/tiktok/scheduled", 409, "has passed"),
    ],
)
def test_refused_scheduling(client: TestClient, publish_at: str, path: str, status: int, detail: str):
    put(client, tiktok_manifest(publish_at))
    response = client.post(f"{URL}{path}")
    assert response.status_code == status
    assert detail in response.json()["detail"]
