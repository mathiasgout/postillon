# Add a platform

A platform is a package `postillon/platforms/<name>/`. The post and the account settings
load without any platform SDK, so that the API validates a submission without the
platform's extra; only the worker imports the client.

```
postillon/platforms/<name>/
  __init__.py   re-exports the post and the account settings
  post.py       the post, a Pydantic model
  settings.py   the settings of an account, a Pydantic model
  client.py     the client, which talks to the platform
```

## The post

A subclass of `PlatformPost` (`postillon/platforms/base.py`) that sets `name` and declares
the platform's fields after the inherited `account`, with their rules as constraints and
validators. The model is strict and refuses unknown fields.

```python
class ExamplePost(PlatformPost):
    name: ClassVar[str] = "example"

    caption: Annotated[str, StringConstraints(max_length=2200)] = ""
```

A platform the service cannot publish to sets `manual` to `True`: the operator schedules
its posts and marks them scheduled through the API (see `api.md`), and its client only
follows `publish_at`, as `tiktok.md` describes.

Register it in `POSTS` (`postillon/platforms/__init__.py`) and as a field of `Posts`
(`postillon/manifest.py`).

## The account settings

A frozen Pydantic model that refuses unknown fields. Secrets are never settings: an account
names the environment variable that holds each of them (see `environment.md`). Add it as a
field of `ProjectSettings` (`postillon/settings.py`), a mapping of account names to settings.

## The client

A class that takes the accounts of one project, checks at construction that their secrets
are set, raising `ValueError` otherwise, and implements `Platform.step`: it receives a
`Task` and returns the post's new `PostState`.

| `Task` attribute | Meaning |
| --- | --- |
| `post` | The post, the platform's model. |
| `publish_at` | The entry's publication time, in UTC. |
| `state` | The post's current state: `status`, `remote_id`, `error`, `extra`. |
| `now` | The time of the pass. |
| `video.file()` | The video as a local MP4 file. |
| `video.url(expires_seconds)` | A signed URL the platform can fetch the video from. |
| `checkpoint(state)` | Records a state at once, such as `in_progress` before a long upload. |
| `next_publish_at` | The publication time of the next entry with a post on the same platform and account, `None` if there is none. |

The client decides when it acts: it may return `task.state` unchanged until `publish_at`.
It records the platform's identifier of the video in `remote_id`, and what it keeps between
two steps in `extra`, documented in the platform's document. An expected refusal returns
`failed` or `rejected` with an `error`; any exception counts as `failed` (see `statuses.md`).

A client whose credentials expire also implements `check_credentials(now)`
(`ChecksCredentials`): the worker calls it once a day for every client, whether a post waits
or not. It renews the credentials that are due or warns before they expire, logs a failure
and keeps the current credentials.

`load_platforms` (`postillon/platforms/loader.py`) builds the client when the project has an
account of the platform. The SDK goes in an extra of `pyproject.toml` named after the
platform, and the platform's document in `docs/<name>.md`, on the model of `youtube.md`.
