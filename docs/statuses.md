# Statuses

Each post of an entry has a status, which the worker changes as it acts on the platform.
Every change is recorded as an event of the post (see `api.md`), except during the retries
of a `failed` post: its history holds the first failure, then the outcome of the attempt
that succeeds or rejects it, and the post itself carries the count and the latest error.

| Status | Meaning |
| --- | --- |
| `pending` | Nothing sent to the platform yet. |
| `in_progress` | An operation started and its outcome is unknown; the platform resolves it on the next pass before sending anything again. |
| `scheduled` | The platform holds the video and publishes it at `publish_at` by itself. On a manual platform, the operator says so through the API (see `api.md`). |
| `published` | The video is public. Final. |
| `failed` | The latest attempt failed; the worker tries again later. |
| `rejected` | The platform refuses the post, or its account is no longer configured; nothing is tried again until the entry is submitted again. |

`in_progress`, `scheduled` and `published` posts may have reached their platform: a new
submission leaves them as they are, with the content and the publication time they were
sent with, and the API says they are `outdated` when the manifest no longer matches them
(see `api.md`).

## Who changes a status

| Actor | Change |
| --- | --- |
| Producer | Creates a post `pending` by a submission, or `published` by a record; makes a `rejected` post `pending` by submitting the entry again. |
| Operator | Makes a `pending` post of a manual platform `scheduled`, before `publish_at`, once the entry has its video. |
| Worker | Gives a `pending`, `in_progress`, `failed` or `scheduled` post the status its platform returns. |

The service refuses any other change (see `api.md`).

## When the worker steps a post

The worker runs a pass every `poll_seconds` (see `configuration.md`) and hands every post
that has something due to its platform:

- a `pending` post, on every pass while the service holds the entry's video; the
  platform decides when it acts, and may leave the post unchanged until `publish_at`;
- an `in_progress` post, on every pass;
- a `failed` post, once its retry delay has passed since its latest change and while the
  service holds the video: 1 minute after the first failure, twice as long after each new
  one, 1 hour at most; the intermediate state of an attempt keeps the count;
- a `scheduled` post, once its `publish_at` is reached, for the platform to confirm the
  publication;
- never a `published` or `rejected` post.

A refusal the platform documents as final rejects the post; any other error, an exception
included, leaves it `failed`. Before a long operation, the platform records an intermediate
state, so that an interruption at any point never sends the video twice.

A post's `publish_at` is the entry's until the post is sent, then the one it was sent with.

## The video

An entry exists from its manifest on, and its posts stay `pending` until it receives a
video (see `api.md`). The service holds the video on its disk, under a name that carries
its SHA-256, and copies it to the bucket only when a platform fetches it by URL (see
`bucket.md`). Once every post of the entry is `scheduled` or `published`, the worker deletes
both copies and dates the video's `released_at`; a post added afterwards waits for a new
video. A `rejected` post keeps the video.

## API and worker together

The API and the worker are two processes sharing the database. Each entry and each post
carries a version number: a write based on a row the other process changed meanwhile is
dropped, and the worker tries again on its next pass, or the API answers `409`
`changed-meanwhile`.
