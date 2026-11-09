# Add a platform

A platform is a package `postillon/platforms/<name>/` that declares itself once. The
declaration, the post and the account settings load without any platform SDK, so that the
API validates a submission without the platform's extra; only the worker imports the client.

```
postillon/platforms/<name>/
  __init__.py   the declaration, PLATFORM
  post.py       the post, a Pydantic model
  settings.py   the settings of an account, a Pydantic model
  client.py     the client, which talks to the platform
```

## The declaration

`PLATFORM`, a `PlatformSpec` (`postillon/platforms/base.py`), added to the tuple of
`PLATFORMS` (`postillon/platforms/__init__.py`), whose order is the order an entry lists its
posts. The manifest takes a field `posts.<name>` from it, the configuration a table
`projects.<project>.<name>`, and the worker the client of every project with an account of
the platform.

| Field | Meaning |
| --- | --- |
| `name` | The platform's name in a manifest, the configuration and the API. |
| `post` | The post model. |
| `account` | The account settings model. |
| `client` | A function that imports the client and builds it from the project's accounts of the platform. |
| `manual` | `True` when the service cannot publish to the platform, `False` by default. |
| `extra` | The extra of `pyproject.toml` holding the client's SDK, `None` when it needs none. |

```python
def _client(accounts: Mapping[str, ExampleAccount]) -> Platform:
    from postillon.platforms.example.client import ExamplePlatform

    return ExamplePlatform(accounts)


PLATFORM = PlatformSpec(name="example", post=ExamplePost, account=ExampleAccount, client=_client, extra="example")
```

The client is imported inside the function, never at the top of the module: the API loads
the declaration without the extra.

A manual platform: the operator schedules its posts and marks them scheduled through the
API (see `api.md`), and its client only follows `publish_at`, as `tiktok.md` describes.

## The post

A subclass of `PlatformPost` (`postillon/platforms/base.py`) that declares the platform's
fields after the inherited `account`, with their rules as constraints and validators. The
model is strict and refuses unknown fields.

```python
class ExamplePost(PlatformPost):
    caption: Annotated[str, StringConstraints(max_length=2200)] = ""
```

## The account settings

A frozen Pydantic model that refuses unknown fields. Secrets are never settings: an account
names the environment variable that holds each of them (see `environment.md`).

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

The SDK goes in an extra of `pyproject.toml` named after the platform, which the declaration
names, and the platform's document in `docs/<name>.md`, on the model of `youtube.md`.
