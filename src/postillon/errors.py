"""The refusals of the service: each carries a stable code, and its kind decides the HTTP status the
API answers with (see docs/api.md).

Raised by the services and the storage, translated by a single handler of the API; depends on nothing.
"""

from __future__ import annotations

from typing import ClassVar


class Refused(Exception):
    """A request the service refuses; the message says why, for the client."""

    code: ClassVar[str]


class NotFound(Refused):
    pass


class Invalid(Refused):
    pass


class Conflict(Refused):
    """The request is valid but the current state refuses it."""


class ProjectNotFound(NotFound):
    code = "project-not-found"


class EntryNotFound(NotFound):
    code = "entry-not-found"


class PostNotFound(NotFound):
    code = "post-not-found"


class VideoNotFound(NotFound):
    code = "video-not-found"


class AccountNotConfigured(Invalid):
    code = "account-not-configured"


class VideoMissing(Invalid):
    code = "video-missing"


class VideoTooLarge(Invalid):
    code = "video-too-large"


class VideoNotMp4(Invalid):
    code = "video-not-mp4"


class PlatformNotManual(Invalid):
    code = "platform-not-manual"


class PublicationsMismatch(Invalid):
    code = "publications-mismatch"


class PublicationInFuture(Invalid):
    code = "publication-in-future"


class EntryExists(Conflict):
    code = "entry-exists"


class PostChanged(Conflict):
    """Another process changed a post meanwhile; nothing is written, and the request may be sent again."""

    code = "post-changed"


class TransitionRefused(Conflict):
    code = "transition-refused"


class PublishAtPassed(Conflict):
    code = "publish-at-passed"
