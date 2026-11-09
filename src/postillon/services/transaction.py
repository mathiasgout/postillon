"""The end of a request's transaction: the API commits once the services have written, and turns a
concurrent write into a refusal (see docs/statuses.md)."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from postillon.errors import ChangedMeanwhile


def commit(session: Session) -> None:
    """Commits what the request wrote; raises ChangedMeanwhile, having written nothing, when another
    process changed or created the same rows since they were read."""
    try:
        session.commit()
    except (StaleDataError, IntegrityError):
        session.rollback()
        raise ChangedMeanwhile("the entry changed meanwhile, send the request again") from None
