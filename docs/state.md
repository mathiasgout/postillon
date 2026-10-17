# State

The service records where each entry stands at `<project>/states/<entry>.json` (see
`bucket.md`), and reads it back on every pass to know what is left to do. It is the only
writer and the only reader of this object: a producer may look at it, but never has to.

```json
{
  "version": 1,
  "manifest_sha256": "9f2c…",
  "error": null,
  "platforms": {
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
| `platforms.<name>.status` | Where the platform stands (see below). |
| `platforms.<name>.manifest_sha256` | SHA-256 of the manifest this platform status reflects. |
| `platforms.<name>.remote_id` | Identifier of the video on the platform, once known. |
| `platforms.<name>.updated_at` | Last change of this platform entry, RFC 3339 in UTC. |
| `platforms.<name>.error` | Last failure or rejection reason, `null` otherwise. |

A platform document may add fields to its block (see `youtube.md`).

## Statuses

| Status | Meaning |
| --- | --- |
| `pending` | Nothing sent to the platform yet. |
| `in_progress` | An operation started and its outcome is unknown; the adapter resolves it on the next pass before sending anything again. |
| `scheduled` | The platform holds the video and publishes it at `publish_at` by itself. |
| `published` | The video is public. Final. |
| `failed` | The last attempt failed; the service retries on later passes. |
| `rejected` | The account is not configured, or the platform refuses the block, such as an unknown category; nothing is retried until the manifest changes. |

## Manifest changes

When the top-level `manifest_sha256` differs from a platform's `manifest_sha256`, that
platform has not applied the latest manifest yet:

- **Before publication** (`pending`, `scheduled`, `failed`, `rejected`), the service applies
  the new manifest on the next pass, and the two digests match again.
- **After publication** (`published`), the change has no effect and the digests stay
  apart.
