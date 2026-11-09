"""The refusals of the service: each carries a stable code, the `type` of its problem response, and
its class decides the HTTP status (see docs/api.md).

Raised by the services and the storage, translated by a single handler of the API; depends on nothing.
"""

from __future__ import annotations

from typing import ClassVar


class Refused(Exception):
    """A request the service refuses, having written nothing; the message says why, for the client."""

    code: ClassVar[str]


class NotFound(Refused):
    pass


class Gone(Refused):
    pass


class Invalid(Refused):
    pass


class Conflict(Refused):
    """The request is valid but the current state refuses it."""


class PreconditionFailed(Refused):
    code = "precondition-failed"


class ProjectNotFound(NotFound):
    code = "project-not-found"


class EntryNotFound(NotFound):
    code = "entry-not-found"


class PostNotFound(NotFound):
    code = "post-not-found"


class VideoNotFound(NotFound):
    code = "video-not-found"


class VideoReleased(Gone):
    code = "video-released"


class AccountNotConfigured(Invalid):
    code = "account-not-configured"


class PlatformNotManual(Invalid):
    code = "platform-not-manual"


class PublicationsMismatch(Invalid):
    code = "publications-mismatch"


class PublicationInFuture(Invalid):
    code = "publication-in-future"


class InvalidFilter(Invalid):
    code = "invalid-filter"


class InvalidOrderBy(Invalid):
    code = "invalid-order-by"


class InvalidPageToken(Invalid):
    code = "invalid-page-token"


class VideoTooLarge(Invalid):
    code = "video-too-large"


class UnsupportedMediaType(Invalid):
    code = "unsupported-media-type"


class VideoNotMp4(UnsupportedMediaType):
    code = "video-not-mp4"


class EntryExists(Conflict):
    code = "entry-exists"


class ChangedMeanwhile(Conflict):
    """Another process changed the entry or one of its posts meanwhile; nothing is written, and the
    request may be sent again."""

    code = "changed-meanwhile"


class TransitionRefused(Conflict):
    code = "transition-refused"


class PublishAtPassed(Conflict):
    code = "publish-at-passed"


class VideoNotHeld(Conflict):
    """The service holds no video of the entry, which the operator could not have scheduled."""

    code = "video-not-held"
