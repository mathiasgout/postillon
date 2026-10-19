import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from postillon.manifest import Manifest, Posts
from postillon.platforms import POSTS
from postillon.platforms.instagram import InstagramPost
from postillon.platforms.youtube import YouTubePost


def manifest(**posts: Any) -> str:
    return json.dumps({"publish_at": "2026-10-22T18:00:00Z", "posts": posts or {"youtube": youtube()}})


def youtube(**fields: Any) -> dict[str, Any]:
    return {"account": "main", "title": "Day 23", **fields}


def test_manifest_lists_its_posts_by_platform():
    parsed = Manifest.model_validate_json(manifest(youtube=youtube(), instagram={"account": "main"}))
    assert list(parsed.posts.by_platform()) == ["youtube", "instagram"]
    assert parsed.publish_at == datetime(2026, 10, 22, 18, 0, tzinfo=UTC)


def test_publish_at_is_converted_to_utc():
    raw = json.dumps({"publish_at": "2026-10-22T20:00:00+02:00", "posts": {"youtube": youtube()}})
    assert Manifest.model_validate_json(raw).publish_at == datetime(2026, 10, 22, 18, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ('{"publish_at": "2026-10-22T18:00:00", "posts": {"youtube": {"account": "main", "title": "x"}}}', "timezone"),
        ('{"publish_at": "2026-10-22T18:00:00Z", "posts": {}}', "no post"),
        ('{"publish_at": "2026-10-22T18:00:00Z", "posts": {"tiktok": {"account": "main"}}}', "tiktok"),
        (
            '{"publish_at": "2026-10-22T18:00:00Z", "posts": {"youtube": {"account": "main", "title": "x"}}, "v": 1}',
            "v",
        ),
        ("not json", "Invalid JSON"),
    ],
)
def test_invalid_manifests(raw: str, message: str):
    with pytest.raises(ValidationError, match=message):
        Manifest.model_validate_json(raw)


def test_posts_and_registry_name_the_same_platforms():
    assert set(Posts.model_fields) == set(POSTS)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"title": ""}, "at least 1 character"),
        ({"title": "   "}, "blank"),
        ({"title": "x" * 101}, "at most 100 characters"),
        ({"title": "a <b>"}, "< or >"),
        ({"description": "é" * 2501}, "5002 bytes"),
        ({"category_id": "music"}, "pattern"),
        ({"made_for_kids": "false"}, "boolean"),
        ({"account": "Main"}, "pattern"),
        ({"tags": ["x"]}, "Extra inputs"),
    ],
)
def test_invalid_youtube_posts(fields: dict[str, Any], message: str):
    with pytest.raises(ValidationError, match=message):
        YouTubePost.model_validate(youtube(**fields))


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"caption": "x" * 2201}, "at most 2200 characters"),
        ({"caption": " ".join(f"#tag{i}" for i in range(31))}, "31 hashtags"),
        ({"caption": " ".join(f"@user{i}" for i in range(21))}, "21 mentions"),
        ({"share_to_feed": "yes"}, "boolean"),
        ({"thumb_offset": -1}, "greater than or equal to 0"),
        ({"thumb_offset": True}, "integer"),
    ],
)
def test_invalid_instagram_posts(fields: dict[str, Any], message: str):
    with pytest.raises(ValidationError, match=message):
        InstagramPost.model_validate({"account": "main", **fields})


def test_instagram_limits_are_inclusive():
    caption = " ".join(f"#tag{i}" for i in range(30)) + " " + " ".join(f"@user{i}" for i in range(20))
    InstagramPost.model_validate({"account": "main", "caption": caption})
    InstagramPost.model_validate({"account": "main", "caption": "x" * 2200})


def test_a_hash_inside_a_word_is_no_hashtag():
    InstagramPost.model_validate({"account": "main", "caption": "C#" * 40})
