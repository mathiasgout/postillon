import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from postillon import Entry
from postillon.platforms.youtube import YouTube

WHEN = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)


def youtube(**fields):
    return YouTube(**{"account": "my-youtube", "title": "Pasta in ten minutes", **fields})


def entry(**fields):
    return Entry(**{"id": "pasta-in-ten-minutes", "publish_at": WHEN, "posts": [youtube()], **fields})


def manifest(**fields):
    data = {
        "version": 1,
        "publish_at": "2026-10-19T06:00:00Z",
        "posts": {"youtube": {"account": "my-youtube", "title": "Pasta in ten minutes"}},
        **fields,
    }
    return json.dumps(data).encode()


def test_manifest_round_trip():
    original = entry(posts=[youtube(description="A quick weeknight recipe.", category_id="26")])
    assert Entry.from_manifest(original.id, original.to_manifest()) == original


def test_manifest_leaves_out_unset_optional_fields():
    data = json.loads(entry().to_manifest())
    assert data == {
        "version": 1,
        "publish_at": "2026-10-19T06:00:00Z",
        "posts": {"youtube": {
            "account": "my-youtube",
            "title": "Pasta in ten minutes",
            "description": "",
            "category_id": "22",
            "made_for_kids": False,
            "contains_synthetic_media": False,
        }},
    }


def test_publish_at_is_written_in_utc():
    paris = timezone(timedelta(hours=2))
    data = json.loads(entry(publish_at=datetime(2026, 10, 19, 8, 0, tzinfo=paris)).to_manifest())
    assert data["publish_at"] == "2026-10-19T06:00:00Z"


@pytest.mark.parametrize("entry_id", ["season-1/day-16", "a_b", "x"])
def test_valid_entry_ids(entry_id):
    entry(id=entry_id).validate()


@pytest.mark.parametrize("entry_id", ["", "Pasta", "a b", "/a", "a/", "a//b", "a.json"])
def test_invalid_entry_ids(entry_id):
    with pytest.raises(ValueError, match="entry id"):
        entry(id=entry_id).validate()


@pytest.mark.parametrize(("fields", "message"), [
    ({"publish_at": datetime(2026, 10, 19, 6, 0)}, "time zone"),
    ({"posts": []}, "no post"),
    ({"posts": [youtube(), youtube()]}, "appears twice"),
])
def test_invalid_entries(fields, message):
    with pytest.raises(ValueError, match=message):
        entry(**fields).to_manifest()


@pytest.mark.parametrize(("fields", "message"), [
    ({"account": "My YouTube"}, "account"),
    ({"title": " "}, "title is empty"),
    ({"title": "x" * 101}, "101 characters"),
    ({"description": "é" * 2501}, "5002 bytes"),
    ({"title": "a <b>"}, "title contains"),
    ({"description": "a > b"}, "description contains"),
    ({"category_id": "music"}, "category_id"),
    ({"made_for_kids": "no"}, "boolean"),
])
def test_invalid_youtube_posts(fields, message):
    with pytest.raises(ValueError, match=message):
        youtube(**fields).validate()


def test_youtube_limits_are_inclusive():
    youtube(title="x" * 100, description="é" * 2500).validate()


@pytest.mark.parametrize(("raw", "message"), [
    (b"{", "not valid JSON"),
    (b"[]", "JSON object"),
    (manifest(extra=1), "unknown fields"),
    (json.dumps({"version": 1, "publish_at": "2026-10-19T06:00:00Z"}).encode(), "missing fields"),
    (manifest(version=2), "manifest version"),
    (manifest(publish_at="2026-10-19T08:00:00+02:00"), "Z suffix"),
    (manifest(publish_at="tomorrowZ"), "not RFC 3339"),
    (manifest(posts=[]), "posts must be"),
    (manifest(posts={"tiktok": {}}), "unknown platform"),
    (manifest(posts={"youtube": {"account": "my-youtube", "title": "t", "tags": []}}), "unknown fields"),
    (manifest(posts={"youtube": {"account": "my-youtube"}}), "missing fields"),
    (manifest(posts={"youtube": {"account": "my-youtube", "title": "x" * 101}}), "101 characters"),
])
def test_invalid_manifests(raw, message):
    with pytest.raises(ValueError, match=message):
        Entry.from_manifest("pasta-in-ten-minutes", raw)
