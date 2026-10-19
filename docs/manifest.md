# Manifest

The manifest describes one entry: its publication time and one post per platform, with its
account and texts. It is the `entry` part of a submission (see `api.md`).

```json
{
  "publish_at": "2026-10-22T18:00:00Z",
  "posts": {
    "youtube": {
      "account": "main",
      "title": "Pasta in ten minutes",
      "description": "A quick weeknight recipe.\n#cooking #pasta"
    },
    "instagram": {
      "account": "main",
      "caption": "Pasta in ten minutes #cooking"
    }
  }
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `publish_at` | string | Publication time, RFC 3339 with a time zone; kept in UTC. |
| `posts` | object | One post per platform, keyed by platform name: `youtube`, `instagram`. |

Each post names in `account` an account declared for its platform under the project (see
`configuration.md`), and carries the fields of its platform, described by the platform's
document: `youtube.md`, `instagram.md`.

## Validation

The API refuses a manifest that is not JSON, lacks a field, carries an unknown one, has a
`publish_at` without time zone, no post, an unknown platform, a value of the wrong type
(`"false"` is not a boolean), or a post that breaks its platform's rules, such as a title
over the length limit. It also refuses a post whose account is not configured.
