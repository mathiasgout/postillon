# Instagram

The Instagram platform publishes the video as a Reel at `publish_at`. Instagram cannot
schedule a publication through its API: the worker publishes at the time itself, across a
few passes while Instagram processes the video.

It uses the Instagram API with Facebook Login and needs no other package than postillon:
`postillon[instagram]` declares no dependency.

## Account

An account designates one Instagram professional account linked to a Facebook Page,
authorized by an access token of that Page, issued by a Meta app with the Instagram use case.

```toml
[projects.my-project.instagram.my-instagram]
username = "mychannel"
access_token_env = "MY_INSTAGRAM_TOKEN"
```

| Setting | Required | Meaning |
| --- | --- | --- |
| `username` | yes | Username of the account. The worker refuses a token whose Page is linked to another account. |
| `access_token_env` | yes | Variable holding the Page access token, with the `instagram_basic`, `instagram_content_publish`, `pages_show_list` and `pages_read_engagement` permissions. |

## Get the token

1. In the Graph API Explorer, select the app, add the four permissions and generate a user
   access token, granting the Page and its Instagram account.
2. Extend this token in the Access Token Debugger.
3. With the extended token, read `GET /{page-id}?fields=access_token`: it returns the Page
   access token, which does not expire.
4. Place the Page access token in `.env` (see `environment.md`) and restart the worker.

The worker refuses to start when the variable is missing.

## Data access

Meta cuts a token's data access 90 days after the user last granted the app. Once a day,
whether a post waits or not, the worker reads when each account's token loses its data
access (`debug_token`) and logs it: as information, as a warning within 14 days of that
date, and as an error once the access is lost or the token is invalid. Getting the token
again restores the access.

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
| `account` | yes | Account name, declared under the project in the configuration. |
| `caption` | no | Reel caption, 2200 characters, 30 hashtags and 20 mentions at most. Empty by default. |
| `share_to_feed` | no | Whether the Reel also appears in the feed, `true` by default. |
| `thumb_offset` | no | Frame of the video used as cover, in milliseconds from the start, `0` by default. |

The video meets the Reels specifications of Instagram: MP4 with H.264 or HEVC video and
AAC audio, 3 seconds to 15 minutes, 300 MB at most, 9:16 recommended.

## Behavior

- **Before `publish_at`**, the post stays `pending`.
- **At `publish_at`**, or at the first pass after it, the platform creates a Reel container
  from a signed URL of the video copied to the bucket, valid one hour, and the post is
  `in_progress`.
- **A missed `publish_at`**: when the next entry of the project with an Instagram post on
  the same account is due as well, such as after the worker was stopped, the post is
  `rejected` without creating a container. Only the last due Reel of the account is
  published.
- **On the next passes**, the platform reads the container's status and publishes it once
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
and its publication, `extra` carries `container_id`.
