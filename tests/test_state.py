import json
from datetime import UTC, datetime

from postillon.state import EntryState, PostState, Status


def test_state_round_trip_keeps_platform_fields():
    state = EntryState(
        manifest_sha256="abc",
        posts={"youtube": PostState(
            status=Status.SCHEDULED,
            manifest_sha256="abc",
            remote_id="aBcD3fGh1jK",
            updated_at=datetime(2026, 10, 17, 19, 2, 11, tzinfo=UTC),
            extra={"container_id": "123"},
        )},
    )
    assert EntryState.from_json(state.to_json()) == state


def test_state_json_follows_the_documented_shape():
    state = EntryState(manifest_sha256="abc", posts={"youtube": PostState(
        status=Status.FAILED, manifest_sha256="abc", updated_at=datetime(2026, 10, 17, tzinfo=UTC), error="quota",
    )})
    assert json.loads(state.to_json()) == {
        "version": 1,
        "manifest_sha256": "abc",
        "error": None,
        "posts": {"youtube": {
            "status": "failed",
            "manifest_sha256": "abc",
            "remote_id": None,
            "updated_at": "2026-10-17T00:00:00Z",
            "error": "quota",
        }},
    }
