# Add a platform

A platform is a package `postillon/platforms/<name>/` with two modules. The core never
changes: it finds the post by its name and the adapter by convention.

```
postillon/platforms/<name>/
  __init__.py   re-exports the post
  post.py       the post, used by producers and the service
  adapter.py    the adapter, used by the service only
```

## The post

A frozen dataclass that subclasses `Post`, sets `name`, declares the platform's fields
after the inherited `account`, and checks them in `validate()`, which raises `ValueError`.
It imports no platform SDK, since producers install none.

```python
@dataclasses.dataclass(frozen=True, kw_only=True)
class Example(Post):
    name = "example"

    caption: str

    def validate(self) -> None:
        super().validate()
        if len(self.caption) > 2200:
            raise ValueError("example: caption over 2200 characters")
```

Register it in `POSTS` in `postillon/platforms/__init__.py`.

## The adapter

The module `adapter.py` defines a class named `Adapter`:

- **`Adapter(accounts)`** receives the settings of the platform's accounts in one project
  (see `configuration.md`), keyed by account name, and raises `ValueError` on an invalid
  setting. The service builds one adapter per project and platform at start.
- **`step(task)`** returns the post's new state. The service calls it as described in
  `state.md`, with a `Task` from `postillon.adapter`:

| Attribute | Meaning |
| --- | --- |
| `entry` | The entry, with its `publish_at`. |
| `post` | The post of this platform. |
| `state` | The post's current state. |
| `now` | The time of the pass. |
| `video.file()` | The video as a local MP4 file, downloaded once per pass. |
| `video.url(expires_seconds)` | A signed URL the platform can fetch the video from. |
| `checkpoint(state)` | Records a state at once, such as `in_progress` before a long upload. |

A platform whose accounts need an authorization defines a function
**`login(account, settings)`** in the same module. It receives the account's name and
settings, obtains its secrets, interactively if needed, and returns them by variable name;
`postillon login` writes them to `.env`. It raises `ValueError` on a refusal.

The adapter decides when it acts: it may return `task.state` unchanged until
`publish_at`. It records the platform's identifier of the video in `remote_id`, and any
further field in `extra`, documented in the platform's document. An expected failure
returns `failed` or `rejected` with an `error`; any exception is caught by the service
and recorded as `failed`.

The platform's SDK goes in an extra of `pyproject.toml` named after the platform, and its
document in `docs/<name>.md`, on the model of `youtube.md`.
