# API

The API serves JSON under `/v1`; an interactive description of every route is served at
`/docs`. It has no authentication: it is served on a trusted network only.

| Route | Purpose |
| --- | --- |
| `PUT /v1/projects/{project}/entries/{key}` | Create or replace an entry. |
| `POST /v1/projects/{project}/entries/{key}/record` | Record an entry published outside the service. |
| `GET /v1/projects/{project}/entries/{key}` | An entry, its posts and their history. |
| `GET /v1/projects/{project}/entries/{key}.mp4` | The video of an entry. |
| `POST /v1/projects/{project}/entries/{key}/posts/{platform}/scheduled` | Mark a post of a manual platform scheduled. |
| `GET /v1/entries` | The entries, latest publication time first. |
| `GET /health` | `{"status": "ok"}` while the API serves. |
| `GET /` | The administration pages (see `admin-page.md`). |

## Names

| Name | Rule |
| --- | --- |
| `project` | `[a-z0-9-]+`, declared in the configuration (see `configuration.md`). |
| `key` | `[a-z0-9_-]+` segments joined by `/`, 200 characters at most; unique within its project and never reused. |

## Create or replace an entry

`PUT /v1/projects/{project}/entries/{key}`, as `multipart/form-data`:

| Part | Required | Content |
| --- | --- | --- |
| `entry` | yes | The manifest, as JSON text (see `manifest.md`). |
| `video` | while the service holds no video of the entry | The video, an MP4 file within `max_video_bytes` (see `configuration.md`). |

A submission is checked whole before anything is written. On a replacement:

- a post not sent yet (`pending`, `failed`, `rejected`) takes its new content, and a
  `rejected` one is tried again;
- a post that may have reached its platform (`in_progress`, `scheduled`, `published`)
  stays as it was sent; its platform is listed in `ignored` when its content or the
  publication time differ;
- a platform left out of the manifest loses its post when it is not sent yet, and is
  listed in `ignored` otherwise;
- a new video replaces the one the service holds, for the posts not sent yet.

| Status | Meaning |
| --- | --- |
| `201` | Entry created. Body: `{"entry": Entry, "ignored": [platform]}`. |
| `200` | Entry replaced. Same body. |
| `404` | Project not configured. |
| `409` | The worker changed a post of the entry meanwhile; nothing is written, submitting again settles it. |
| `422` | Invalid manifest or name, account not configured for the platform in the project, video missing, not an MP4, or too large. `detail` holds the reason, or the faulty fields with their location in `entry`. |

## Record an entry published outside the service

`POST /v1/projects/{project}/entries/{key}/record`, as JSON, records an entry whose posts
went public without the service, so that its history holds them. The service sends nothing
and holds no video: every post is `published`, and the worker never steps it.

```json
{
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
| `manifest` | yes | The manifest, checked as on a submission (see `manifest.md`). |
| `published` | yes | One publication per post of the manifest, keyed by platform. |
| `published.<platform>.at` | yes | When the post went public, RFC 3339 with a time zone, in the past. |
| `published.<platform>.remote_id` | no | Identifier of the video on the platform. |

Each post has one event, `published` at its `at`; `video_released_at` is the time of the
record.

| Status | Meaning |
| --- | --- |
| `201` | Entry recorded. Body: the entry, as read below. |
| `404` | Project not configured. |
| `409` | The entry exists already; a record never changes an entry. |
| `422` | Invalid manifest or name, account not configured, `published` not naming exactly the platforms of the posts, or a publication time in the future. |

## Read an entry

`GET /v1/projects/{project}/entries/{key}` answers `200` with the entry, or `404`.

| Field | Meaning |
| --- | --- |
| `project`, `key` | The entry's names. |
| `publish_at` | Publication time, in UTC. |
| `manifest` | The latest manifest submitted, with the defaults filled in. |
| `submitted_at`, `updated_at` | First and latest submission. |
| `video_released_at` | When the service deleted its copies of the video, every platform holding it, or recorded the entry; `null` before. |
| `posts` | One post per platform, see below. |

| Post field | Meaning |
| --- | --- |
| `platform`, `account` | Where the post goes. |
| `manual` | `true` when the operator schedules the post on its platform (see `tiktok.md`). |
| `status` | See `statuses.md`. |
| `remote_id` | Identifier of the video on the platform, once known. |
| `error` | Reason of the latest failure or rejection, `null` otherwise. |
| `failures` | Consecutive failures, which space out the retries. |
| `extra` | Fields the platform keeps between two steps (see the platform's document). |
| `updated_at` | Latest change of the post. |
| `events` | Every status the post took, with its `error` and its time `at`, oldest first. |

## Read the video of an entry

`GET /v1/projects/{project}/entries/{key}.mp4` answers `200` with the MP4 file, displayed
inline and named `{project}-{key}.mp4` with `/` turned into `-`, while the service holds
the video; `404` once it is released (`video_released_at`) or when the entry does not
exist.

## Mark a post scheduled

`POST /v1/projects/{project}/entries/{key}/posts/{platform}/scheduled`, without a body,
records that the operator scheduled the post on a manual platform (see `tiktok.md`), which
publishes it at `publish_at`. The post becomes `scheduled`.

| Status | Meaning |
| --- | --- |
| `200` | Post scheduled. Body: the entry, as read above. |
| `404` | The entry has no post on this platform. |
| `409` | The post is no longer `pending`, `publish_at` has passed, or the worker changed it meanwhile. Nothing is written. |
| `422` | The platform is not manual: the worker schedules its posts itself. |

## List entries

`GET /v1/entries` answers a list of entries, as above, latest publication time first.

| Parameter | Meaning |
| --- | --- |
| `project` | Only the entries of this project. |
| `status` | Only the entries with a post of this status. |
| `limit` | 1 to 500, 100 by default. |
| `offset` | Entries to skip, 0 by default. |
