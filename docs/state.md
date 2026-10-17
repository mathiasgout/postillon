# State

The service records where each entry stands at `<project>/states/<entry>.json` (see
`bucket.md`), and reads it back on every pass to know what is left to do. It is the only
writer and the only reader of this object: a producer may look at it, but never has to.

```json
{
  "version": 1,
  "manifest_sha256": "9f2c…",
  "error": null,
  "posts": {
    "youtube": {
      "status": "scheduled",
      "manifest_sha256": "9f2c…",
      "remote_id": "aBcD3fGh1jK",
      "updated_at": "2026-10-17T19:02:11Z",
      "error": null
    }
  }
}
```

## Fields

| Field | Meaning |
| --- | --- |
| `version` | Format version, `1`. |
| `manifest_sha256` | SHA-256 of the manifest bytes the service last read. |
| `error` | Why the whole manifest is rejected, `null` otherwise. |
| `posts.<name>.status` | Where the post stands (see below). |
| `posts.<name>.manifest_sha256` | SHA-256 of the manifest this post status reflects. |
| `posts.<name>.remote_id` | Identifier of the video on the platform, once known. |
| `posts.<name>.updated_at` | Last change of this post, RFC 3339 in UTC. |
| `posts.<name>.error` | Last failure or rejection reason, `null` otherwise. |

A platform document may add fields to the state of its post (see `youtube.md`).

## Statuses

| Status | Meaning |
| --- | --- |
| `pending` | Nothing sent to the platform yet. |
| `in_progress` | An operation started and its outcome is unknown; the adapter resolves it on the next pass before sending anything again. |
| `scheduled` | The platform holds the video and publishes it at `publish_at` by itself. |
| `published` | The video is public. Final. |
| `failed` | The last attempt failed; the service retries on later passes. |
| `rejected` | The account is not configured, or the platform refuses the post, such as an unknown category; nothing is retried until the manifest changes. |

## When the adapter is called

On every pass, the service hands each post to its platform's adapter, except:

- a `published` post, never again;
- a `rejected` post, until the manifest changes;
- a `scheduled` post, until the manifest changes or `publish_at` is reached, when the
  adapter confirms the publication.

A post whose account is not configured is `rejected` without calling the adapter. An
adapter that raises leaves its post `failed`, with the exception as `error`.

## Manifest changes

When the top-level `manifest_sha256` differs from a post's `manifest_sha256`, that post
does not reflect the latest manifest yet:

- **Before publication** (`pending`, `scheduled`, `failed`, `rejected`), the service applies
  the new manifest on the next pass, and the two digests match again.
- **After publication** (`published`), the change has no effect and the digests stay
  apart.
