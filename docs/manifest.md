# Manifest

A manifest describes one entry, a video, and its posts: the publications of that video on
each platform, with their account and texts. `submit` writes it at
`<project>/manifests/<entry>.json`, next to the video (see `bucket.md`); a producer
written in another language writes the same JSON.

```json
{
  "version": 1,
  "publish_at": "2026-10-19T06:00:00Z",
  "posts": {
    "youtube": {
      "account": "my-youtube",
      "title": "Pasta in ten minutes",
      "description": "A quick weeknight recipe.\n#cooking #pasta"
    }
  }
}
```

## Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `version` | integer | Format version, `1`. |
| `publish_at` | string | Publication time, RFC 3339 in UTC (`Z` suffix). |
| `posts` | object | One post per platform to publish on, keyed by platform name. |

Each post names the account to publish with, declared for that platform under the project
in the service configuration, and carries the texts and options of the platform. Its
fields are described by the platform's own document: `youtube.md`, `instagram.md`.

## Validation

Validation runs on both sides, each with what it knows.

- **On submission**, `submit` refuses an entry with a `publish_at` without time zone, no
  post, an unknown platform, two posts on the same platform, or a post that breaks its
  platform's rules, such as a title over the length limit. Nothing is written.
- **In the service**, a manifest that is not valid JSON, has an unknown `version` or an
  unknown field, or breaks any of the rules above, is rejected as a whole and publishes
  nothing. A post whose account is absent from the project's configuration rejects that
  post only. The state records the reason (see `state.md`).
