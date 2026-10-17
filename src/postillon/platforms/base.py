"""A post: the publication of an entry on one platform, with its account, texts and options
(see docs/manifest.md).

Each platform subclasses `Post` in its own package; a post imports no platform SDK, so
that producers install none.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any, ClassVar, Self

# Same alphabet as an entry identifier segment: account names are configuration keys.
ACCOUNT = re.compile(r"[a-z0-9_-]+")


@dataclasses.dataclass(frozen=True, kw_only=True)
class Post:
    name: ClassVar[str]

    account: str

    def validate(self) -> None:
        """Raises ValueError if the post breaks its platform's rules."""
        if not isinstance(self.account, str) or not ACCOUNT.fullmatch(self.account):
            raise ValueError(f"{self.name}: account {self.account!r} must match {ACCOUNT.pattern}")

    def to_dict(self) -> dict[str, Any]:
        """The post as written in the manifest, unset optional fields left out."""
        return {f.name: v for f in dataclasses.fields(self) if (v := getattr(self, f.name)) is not None}

    @classmethod
    def from_dict(cls, data: Any) -> Self:
        """The validated post read from a manifest; raises ValueError on an unknown or missing field."""
        if not isinstance(data, dict):
            raise ValueError(f"{cls.name}: post must be a JSON object")
        fields = {f.name: f for f in dataclasses.fields(cls)}
        unknown = sorted(set(data) - set(fields))
        if unknown:
            raise ValueError(f"{cls.name}: unknown fields {unknown}")
        missing = sorted(
            n for n, f in fields.items()
            if n not in data and f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
        )
        if missing:
            raise ValueError(f"{cls.name}: missing fields {missing}")
        post = cls(**data)
        post.validate()
        return post
