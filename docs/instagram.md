# Instagram

The Instagram adapter publishes the video as a Reel at `publish_at`. Instagram cannot
schedule a publication through its API: the service publishes at the time itself, across
a few passes while Instagram processes the video.

It uses the Instagram API with Instagram Login and needs no other package than postillon:
`postillon[instagram]` declares no dependency.

## Account

An account designates one Instagram professional account, authorized by a long-lived
access token of a Meta app with the Instagram product.

```toml
[projects.my-project.instagram.my-instagram]
username = "mychannel"
access_token_env = "MY_INSTAGRAM_TOKEN"
```

| Setting | Required | Meaning |
| --- | --- | --- |
| `username` | yes | Username of the account. The service refuses a token that authorizes another account. |
| `access_token_env` | yes | Variable holding the account's long-lived access token, with the `instagram_business_basic` and `instagram_business_content_publish` permissions. |

The operator generates the token in the app dashboard and places it in `.env` (see
`environment.md`). The service refuses to start when the variable is missing.

## Token renewal

A long-lived token expires 60 days after it was issued or last renewed. The service renews
each token when it is a week old, and keeps the renewed token in `instagram-tokens.json`
in the working directory, readable by its owner only. A token placed in `.env` replaces
the renewed one: the service uses a renewed token only while the variable still holds
the token it was renewed from.

The service renews a token when it handles a post of its account, on every pass while an
entry waits for its publication. An account with no entry for 60 days needs a new token
in `.env`.

## Post

```json
"instagram": {
  "account": "my-instagram",
  "caption": "Pasta in ten minutes.\n#cooking #pasta",
  "share_to_feed": true,
  "thumb_offset": 0
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `account` | yes | Account name, declared under the project in the service configuration. |
| `caption` | no | Reel caption, 2200 characters, 30 hashtags and 20 mentions at most. Empty by default. |
| `share_to_feed` | no | Whether the Reel also appears in the feed, `true` by default. |
| `thumb_offset` | no | Frame of the video used as cover, in milliseconds from the start, `0` by default. |

The video meets the Reels specifications of Instagram: MP4 with H.264 or HEVC video and
AAC audio, 3 seconds to 15 minutes, 300 MB at most, 9:16 recommended.

## Behavior

- **Before `publish_at`**, the post stays `pending`.
- **At `publish_at`**, or at the first pass after it, the adapter creates a Reel container
  from a signed URL of the video in the bucket, valid one hour, and the post is
  `in_progress`.
- **On the next passes**, the adapter reads the container's status and publishes it once
  Instagram has processed the video; the post is then `published`.
- **Failures**: a container Instagram cannot process rejects the post. A container that
  expires leaves the post `failed`, and the next pass creates a new one. Rate limits,
  temporary errors and an invalid token leave the post `failed`, retried on later passes.
  Any other refusal from Instagram rejects the post.

A container created but never published expires after 24 hours and publishes nothing,
so an interruption at any point never publishes the video twice.

## State

`remote_id` holds the Instagram media identifier; it stays `null` when the publication was
confirmed by the container after an interruption. Between the creation of the container
and its publication, the state carries `container_id`.
