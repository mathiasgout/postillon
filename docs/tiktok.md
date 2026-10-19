# TikTok

The TikTok platform is manual: the service sends nothing to TikTok. The operator schedules
the video in TikTok Studio at `publish_at`, then marks the post scheduled from the
administration page (see `admin-page.md`); the worker only follows the publication time.

TikTok leaves no other way: its Content Posting API publishes to private accounts only
for an unaudited client, and its audit turns down tools that post to accounts their
operator manages. Driving TikTok Studio by script would expose the account to suspension.

It needs no other package than postillon and holds no credentials.

## Account

An account designates one TikTok account the operator schedules videos on.

```toml
[projects.my-project.tiktok.my-tiktok]
handle = "@mychannel"
```

| Setting | Required | Meaning |
| --- | --- | --- |
| `handle` | yes | Handle of the account, starting with `@`, shown to the operator. |

## Post

```json
"tiktok": {
  "account": "my-tiktok",
  "caption": "Pasta in ten minutes #cooking"
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `account` | yes | Account name, declared under the project in the configuration. |
| `caption` | no | Caption the operator pastes in TikTok Studio, 2200 UTF-16 code units at most (an emoji may count two). Empty by default. |

## Behavior

1. The post stays `pending` while the operator schedules it in TikTok Studio, from the
   video, the caption and `publish_at` the administration page shows (see `admin-page.md`).
2. The operator marks it scheduled, from the page or the API
   (`POST /v1/projects/{project}/entries/{key}/posts/tiktok/scheduled`), which accepts it
   before `publish_at` only. The post is `scheduled`.
3. At `publish_at`, a `scheduled` post becomes `published`, on the operator's word: the
   service reads nothing from TikTok. A post still `pending` is `rejected`, with the error
   `not scheduled by the operator before publish_at`.

A post marked scheduled is sent: a new submission leaves it as it is, its new caption or
publication time listed in `ignored` (see `api.md`), and the operator changes it in TikTok
Studio by hand.

## State

The platform keeps no `remote_id` and no `extra`.
