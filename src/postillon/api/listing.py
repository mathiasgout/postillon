"""The parameters of the API's lists: the filter, a subset of AIP-160, the order, and the opaque page
tokens (see docs/api.md).

Only module that reads them; it hands the services plain conditions.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import json
import re
from datetime import UTC, datetime
from typing import Any

from postillon.domain import Status
from postillon.errors import InvalidFilter, InvalidOrderBy, InvalidPageToken
from postillon.platforms import PLATFORMS
from postillon.services.entries import EntryQuery

CONDITION = re.compile(r'^\s*(?P<field>[a-z_.]+)\s*(?P<op><=|>=|!=|=|<|>)\s*(?P<value>"[^"]*"|true|false)\s*$')
CONJUNCTION = re.compile(r"\s+AND\s+")
ORDERS = {"publish_at": False, "publish_at desc": True}


def entry_query(project: str | None, filter_: str, order_by: str, page_token: str, page_size: int) -> EntryQuery:
    """The query of one page of entries; raises InvalidFilter, InvalidOrderBy or InvalidPageToken."""
    order = " ".join(order_by.split()) or "publish_at desc"
    if order not in ORDERS:
        raise InvalidOrderBy(f"order_by takes {' or '.join(repr(o) for o in ORDERS)}, not {order_by!r}")
    query = EntryQuery(project=project, descending=ORDERS[order], limit=page_size, **_conditions(filter_))
    if page_token:
        after = _read_token(page_token, {"project": project, "filter": filter_, "order_by": order})
        try:
            query = dataclasses.replace(query, after=(datetime.fromisoformat(after[0]), int(after[1])))
        except (TypeError, ValueError, IndexError, KeyError):
            raise InvalidPageToken("page_token is not one this list returned") from None
    return query


def entry_token(project: str | None, filter_: str, order_by: str, publish_at: datetime, entry_id: int) -> str:
    order = " ".join(order_by.split()) or "publish_at desc"
    return _write_token({"project": project, "filter": filter_, "order_by": order}, [publish_at.isoformat(), entry_id])


def event_after(scope: dict[str, Any], page_token: str) -> int | None:
    """The id of the last event of the previous page; raises InvalidPageToken."""
    if not page_token:
        return None
    after = _read_token(page_token, scope)
    if not isinstance(after, int):
        raise InvalidPageToken("page_token is not one this list returned")
    return after


def event_token(scope: dict[str, Any], event_id: int) -> str:
    return _write_token(scope, event_id)


def _conditions(filter_: str) -> dict[str, Any]:
    """The conditions of a filter: comparisons of `publish_at`, and equalities on `posts.status`,
    `posts.platform` and `posts.manual`, which hold for one same post, joined by AND."""
    conditions: dict[str, Any] = {"publish_at": ()}
    if not filter_.strip():
        return conditions
    for part in CONJUNCTION.split(filter_.strip()):
        match = CONDITION.match(part)
        if match is None:
            raise InvalidFilter(f"cannot read {part.strip()!r}: expected <field> <operator> <value>")
        field, op, raw = match["field"], match["op"], match["value"]
        value = raw[1:-1] if raw.startswith('"') else raw == "true"
        if field == "publish_at":
            conditions["publish_at"] += ((op, _time(value)),)
            continue
        if field not in ("posts.status", "posts.platform", "posts.manual"):
            raise InvalidFilter(f"cannot filter on {field!r}: publish_at, posts.status, posts.platform or posts.manual")
        name = field.removeprefix("posts.")
        if op != "=":
            raise InvalidFilter(f"{field} takes = only")
        if name in conditions:
            raise InvalidFilter(f"{field} appears twice")
        conditions[name] = _post_value(name, value)
    return conditions


def _time(value: str | bool) -> datetime:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        raise InvalidFilter(f"publish_at compares to an RFC 3339 time with a time zone, not {value!r}")
    return parsed.astimezone(UTC)


def _post_value(name: str, value: str | bool) -> Status | str | bool:
    if name == "manual":
        if not isinstance(value, bool):
            raise InvalidFilter("posts.manual compares to true or false")
        return value
    if not isinstance(value, str):
        raise InvalidFilter(f"posts.{name} compares to a quoted string")
    if name == "status":
        if value not in Status:
            raise InvalidFilter(f"unknown status {value!r}")
        return Status(value)
    if value not in PLATFORMS:
        raise InvalidFilter(f"unknown platform {value!r}")
    return value


def _write_token(scope: dict[str, Any], after: Any) -> str:
    raw = json.dumps({"scope": scope, "after": after}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _read_token(token: str, scope: dict[str, Any]) -> Any:
    """The position a token holds, provided it was returned for the same list with the same parameters."""
    try:
        data = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    except (binascii.Error, ValueError):
        raise InvalidPageToken("page_token is not one this list returned") from None
    if not isinstance(data, dict) or data.get("scope") != scope or "after" not in data:
        raise InvalidPageToken("page_token belongs to another list or other parameters")
    return data["after"]
