# Statuses

Each post of an entry has a status, which the worker changes as it acts on the platform.
Every change is recorded as an event of the post (see `api.md`).

| Status | Meaning |
| --- | --- |
| `pending` | Nothing sent to the platform yet. |
| `in_progress` | An operation started and its outcome is unknown; the platform resolves it on the next pass before sending anything again. |
| `scheduled` | The platform holds the video and publishes it at `publish_at` by itself. On a manual platform, the operator says so through the API (see `api.md`). |
| `published` | The video is public. Final. |
| `failed` | The latest attempt failed; the worker tries again later. |
| `rejected` | The platform refuses the post, or its account is no longer configured; nothing is tried again until the entry is submitted again. |

`in_progress`, `scheduled` and `published` posts may have reached their platform: a new
submission leaves them as they are.

## When the worker steps a post

The worker runs a pass every `poll_seconds` (see `configuration.md`) and hands every post
that has something due to its platform:

- a `pending` or `in_progress` post, on every pass; the platform decides when it acts,
  and may leave the post unchanged until `publish_at`;
- a `failed` post, once its retry delay has passed since its latest change: 1 minute
  after the first failure, twice as long after each new one, 1 hour at most;
- a `scheduled` post, once `publish_at` is reached, for the platform to confirm the
  publication;
- never a `published` or `rejected` post.

A refusal the platform documents as final rejects the post; any other error, an exception
included, leaves it `failed`. Before a long operation, the platform records an intermediate
state, so that an interruption at any point never sends the video twice.

## The video

The service holds the video on its disk from the submission on, and copies it to the bucket
only when a platform fetches it by URL (see `bucket.md`). Once every post of the entry is
`scheduled` or `published`, the worker deletes both copies and dates `video_released_at`.
A `rejected` post keeps the video.

## API and worker together

The API and the worker are two processes sharing the database. Each post carries a version
number: a write based on a post the other process changed meanwhile is dropped, and the
worker steps the post again on its next pass, or the API answers `409`.
