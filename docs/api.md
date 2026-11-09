# API

The API serves JSON under `/v1`; an interactive description of every route is served at
`/docs`. It has no authentication: it is served on a trusted network only.

| Route | Purpose |
| --- | --- |
| `GET /v1/projects/{project}/entries` | The entries of a project, or of all with `-`, a page at a time. |
| `PUT /v1/projects/{project}/entries/{key}` | Create or replace an entry from its manifest. |
| `GET /v1/projects/{project}/entries/{key}` | An entry, its posts and its video. |
| `POST /v1/projects/{project}/entries:record` | Record an entry published outside the service. |
| `PUT /v1/projects/{project}/entries/{key}/video` | Set the video of an entry. |
| `GET /v1/projects/{project}/entries/{key}/video` | The video of an entry. |
| `GET /v1/projects/{project}/entries/{key}/posts/{platform}` | One post of an entry. |
| `POST /v1/projects/{project}/entries/{key}/posts/{platform}:mark-scheduled` | Mark a post of a manual platform scheduled. |
| `GET /v1/projects/{project}/entries/{key}/posts/{platform}/events` | The history of a post, or of all posts with `-`. |
| `GET /health` | `{"status": "ok"}` while the API serves. |
| `GET /admin/` | The administration pages (see `admin-page.md`); `/` redirects there. |

Only the routes under `/v1` form the contract.

## Conventions

- **Resources.** An entry belongs to a project, and has a video and one post per platform,
  each post a history of statuses. `GET` reads a resource, `PUT` creates or replaces one
  at the name the client chooses, and a list is a `GET` on its collection.
- **Statuses are the service's.** No request writes a status: a change asked by a client is
  a custom method, `POST {resource}:{verb}`, which the service accepts only when the
  status allows it (see `statuses.md`). A custom method acts on a resource that exists.
- **A write answers the resource it acted on**, as a read of it does.
- **Names.** In a path, everything is lowercase and a name of several words is joined by
  `-`; in JSON and in query parameters, by `_`. Times are RFC 3339, answered in UTC.
- **Requests carry their media type**: `application/json` for JSON bodies, `video/mp4` for
  the video; any other answers `415`.

| Name | Rule |
| --- | --- |
| `project` | `[a-z0-9][a-z0-9-]*`, declared in the configuration (see `configuration.md`). |
| `key` | `[a-z0-9_-]+`, 200 characters at most; chosen by the producer, unique within its project and never reused. |
| `platform` | `youtube`, `instagram` or `tiktok`. |

## Errors

Every error answers `application/problem+json` (RFC 9457):

```json
{
  "type": "account-not-configured",
  "title": "Unprocessable Content",
  "status": 422,
  "detail": "account 'other' is not configured for youtube in my-project"
}
```

`type` is stable and identifies the case, `detail` explains it. An error of the HTTP layer,
such as an unknown route, has the type `about:blank`.

| Type | Status | Meaning |
| --- | --- | --- |
| `invalid-request` | 422 | A name, a parameter or a body field is invalid; `errors` lists each one with its location `loc`, its message `msg` and its `type`. |
| `unsupported-media-type` | 415 | The request is not sent with the media type its route takes. |
| `project-not-found` | 404 | The project is not configured. |
| `entry-not-found` | 404 | The entry does not exist. |
| `post-not-found` | 404 | The entry has no post on this platform. |
| `video-not-found` | 404 | The entry has received no video. |
| `video-released` | 410 | Every platform holds the video: the service deleted its copies. |
| `account-not-configured` | 422 | A post names an account not configured for its platform in the project. |
| `video-too-large` | 413 | The video is over `max_video_bytes` (see `configuration.md`). |
| `video-not-mp4` | 415 | The video is not an MP4 file. |
| `platform-not-manual` | 422 | The platform's posts are scheduled by the worker, not by the operator. |
| `publications-mismatch` | 422 | A record does not name exactly the platforms of its posts. |
| `publication-in-future` | 422 | A record holds a publication time in the future. |
| `invalid-filter`, `invalid-order-by`, `invalid-page-token` | 422 | A list parameter cannot be read, or a page token belongs to another list. |
| `entry-exists` | 409 | A record names an entry that exists. |
| `transition-refused` | 409 | The post's status does not allow the change. |
| `publish-at-passed` | 409 | The post's publication time has passed. |
| `video-not-held` | 409 | The service holds no video of the entry, so the operator cannot have scheduled it. |
| `changed-meanwhile` | 409 | Another request or the worker changed the entry meanwhile; nothing is written, and sending the request again settles it. |
| `precondition-failed` | 412 | `If-Match` or `If-None-Match` does not hold (see below). |

## Conditional requests

Every resource answers an `ETag`, which changes with it; an entry's changes with its posts
too, which its representation embeds, and a video's is its SHA-256 in quotes.

- A `GET` with `If-None-Match` naming the current `ETag` answers `304`, without a body.
- A write with `If-Match` applies only if the resource still has this `ETag`, `412`
  otherwise; `If-Match: *` only if it exists.
- A `PUT` with `If-None-Match: *` applies only if the resource does not exist, `412`
  otherwise: a creation that never replaces.

## Create or replace an entry

`PUT /v1/projects/{project}/entries/{key}`, with the manifest as `application/json` (see
`manifest.md`), answers the entry: `201` with its `Location` when it is created, `200` when
it is replaced. A submission is checked whole before anything is written. On a replacement:

- a post not sent yet (`pending`, `failed`, `rejected`) takes its new content and
  publication time, and a `rejected` one is tried again;
- a post that may have reached its platform (`in_progress`, `scheduled`, `published`)
  keeps what it was sent with, and is `outdated` when the manifest differs from it;
- a platform left out of the manifest loses its post when it is not sent yet, and keeps it
  otherwise.

## Set the video of an entry

`PUT /v1/projects/{project}/entries/{key}/video`, with the MP4 file as the body, sent as
`video/mp4`. The entry must exist: the manifest comes first. A `Content-Length` over
`max_video_bytes` is refused before the body is read.

The answer has no body: `201` with its `Location` for the entry's first video, or the first
after a release, and `204` for a replacement; its `ETag` is the video's. Sending the same
bytes again changes nothing. A new video goes to the posts not sent yet; a post that may
have reached its platform keeps the one it was sent with.

## Read an entry

`GET /v1/projects/{project}/entries/{key}` answers `200` with the entry.

| Field | Meaning |
| --- | --- |
| `project`, `key` | The entry's names. |
| `publish_at` | Publication time of the latest manifest. |
| `manifest` | The latest manifest submitted, with the defaults filled in. |
| `submitted_at`, `updated_at` | Creation, and latest manifest or video received. |
| `video` | The latest video received, `null` before the first: its `size` in bytes, its `sha256`, `received_at`, and `released_at`, set once every platform holds it and the service deleted its copies. |
| `posts` | One post per platform, see below. |

## Read the video of an entry

`GET /v1/projects/{project}/entries/{key}/video` answers `200` with the MP4 file, displayed
inline and named `{project}-{key}.mp4`, while the service holds it. It serves byte ranges
and `HEAD`.

## Read a post

`GET /v1/projects/{project}/entries/{key}/posts/{platform}` answers `200` with the post,
the same as in its entry.

| Field | Meaning |
| --- | --- |
| `project`, `key`, `platform` | The post's names. |
| `account` | The account the post goes to. |
| `manual` | `true` when the operator schedules the post on its platform (see `tiktok.md`). |
| `status` | See `statuses.md`. |
| `publish_at` | The entry's publication time while the post is not sent, the one it was sent with afterwards. |
| `outdated` | `true` when the post may have reached its platform with a content or a time the latest manifest no longer has. |
| `remote_id` | Identifier of the video on the platform, once known. |
| `error` | Reason of the latest failure or rejection, `null` otherwise. |
| `failures` | Consecutive failures, which space out the retries. |
| `extra` | Fields the platform keeps between two steps (see the platform's document). |
| `updated_at` | Latest change of the post. |

## Mark a post scheduled

`POST /v1/projects/{project}/entries/{key}/posts/{platform}:mark-scheduled`, without a
body, records that the operator scheduled a `pending` post on its manual platform (see
`tiktok.md`), which publishes it at `publish_at`. The service must hold the entry's video,
which the operator downloads to schedule it. It answers `200` with the post, now
`scheduled`.

## Read the history of a post

`GET /v1/projects/{project}/entries/{key}/posts/{platform}/events`, with `-` for all the
posts of the entry, answers the statuses the posts took, in the order recorded, a page at a
time (see below).

```json
{
  "events": [
    {"project": "my-project", "key": "day-23", "platform": "tiktok", "status": "pending", "error": null, "at": "2026-10-21T09:12:00Z"}
  ],
  "next_page_token": null
}
```

## List entries

`GET /v1/projects/{project}/entries`, with `-` for all projects, answers the entries as
read above, a page at a time.

```json
{"entries": [], "next_page_token": "eyJzY29wZSI6..."}
```

| Parameter | Meaning |
| --- | --- |
| `filter` | Conditions joined by `AND`, see below; every entry by default. |
| `order_by` | `publish_at` for the nearest first, `publish_at desc` for the latest first, the default. |
| `page_size` | 1 to 500, 100 by default. |
| `page_token` | The `next_page_token` of the previous page, with the same other parameters. |

`next_page_token` is `null` on the last page; a list of events pages the same way.

A condition compares a field to a value: a string in double quotes, `true` or `false`.

| Field | Operators | Value |
| --- | --- | --- |
| `publish_at` | `=`, `!=`, `<`, `<=`, `>`, `>=` | An RFC 3339 time with a time zone. |
| `posts.status` | `=` | A status (see `statuses.md`). |
| `posts.platform` | `=` | A platform. |
| `posts.manual` | `=` | `true` or `false`. |

The conditions on `posts.` hold for one same post: the entries with a pending post on a
manual platform, to publish after a time, are

```
posts.manual = true AND posts.status = "pending" AND publish_at > "2026-10-22T00:00:00Z"
```

## Record an entry published outside the service

`POST /v1/projects/{project}/entries:record`, as JSON, records an entry whose posts went
public without the service, so that its history holds them. The service sends nothing and
receives no video: every post is `published`, and the worker never steps it.

```json
{
  "key": "day-12",
  "manifest": {
    "publish_at": "2026-10-12T18:00:00Z",
    "posts": {
      "youtube": {"account": "main", "title": "Pasta in ten minutes"},
      "tiktok": {"account": "main", "caption": "Pasta in ten minutes #cooking"}
    }
  },
  "published": {
    "youtube": {"at": "2026-10-12T18:00:00Z", "remote_id": "dQw4w9WgXcQ"},
    "tiktok": {"at": "2026-10-12T19:30:00Z"}
  }
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `key` | yes | The entry's key, which must not exist. |
| `manifest` | yes | The manifest, checked as on a submission (see `manifest.md`). |
| `published` | yes | One publication per post of the manifest, keyed by platform. |
| `published.<platform>.at` | yes | When the post went public, RFC 3339 with a time zone, in the past. |
| `published.<platform>.remote_id` | no | Identifier of the video on the platform. |

It answers `201` with the entry and its `Location`. Each post has one event, `published` at
its `at`.
