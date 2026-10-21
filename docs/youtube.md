# YouTube

The YouTube platform uploads the video as private with a scheduled publication time
(`publishAt`), so that YouTube publishes it at `publish_at` by itself. It acts on the first
pass after the submission; once uploaded, the video is never modified.

It needs the `youtube` extra: `postillon[youtube]`.

## Account

An account designates one YouTube channel, authorized by a refresh token of an OAuth
client of a Google Cloud project with the YouTube Data API v3 enabled. The project needs
no audit to publish. Uploads have two daily limits: 10 per channel, and 100 per project,
shared by every channel it authorizes.

```toml
[projects.my-project.youtube.my-youtube]
handle = "@mychannel"
refresh_token_env = "MY_YOUTUBE_REFRESH_TOKEN"
```

| Setting | Required | Meaning |
| --- | --- | --- |
| `handle` | yes | Handle of the channel, starting with `@`. The worker refuses a token that authorizes another channel. |
| `refresh_token_env` | yes | Variable holding the channel's refresh token. |
| `client_id_env` | no | Variable holding the OAuth client identifier, `POSTILLON_YOUTUBE_CLIENT_ID` by default. |
| `client_secret_env` | no | Variable holding the OAuth client secret, `POSTILLON_YOUTUBE_CLIENT_SECRET` by default. |

The operator obtains the refresh token from the OAuth 2.0 Playground
(`https://developers.google.com/oauthplayground`), with the client's own credentials and
the `youtube.upload` and `youtube.readonly` scopes granted by the channel owner; the
client is then of type Web application, with that address as an authorized redirect URI.
The operator places the token in `.env` with the client's identifier and secret (see
`environment.md`). The client's consent screen must be in production: in testing, Google revokes refresh tokens after 7
days. The worker refuses to start when one of these variables is missing.

## Post

```json
"youtube": {
  "account": "my-youtube",
  "title": "Pasta in ten minutes",
  "description": "A quick weeknight recipe.\n#cooking #pasta",
  "category_id": "26",
  "made_for_kids": false,
  "contains_synthetic_media": false
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `account` | yes | Account name, declared under the project in the configuration. |
| `title` | yes | Video title, 100 characters at most, without `<` or `>`. |
| `description` | no | Video description, 5000 bytes at most, without `<` or `>`. Empty by default. |
| `category_id` | no | YouTube category, `"22"` (People & Blogs) by default. |
| `made_for_kids` | no | Audience declaration, `false` by default. |
| `contains_synthetic_media` | no | Altered or synthetic content declaration, `false` by default. |

## Behavior

- **Upload**: a post without a video on YouTube is uploaded as private with `publishAt`,
  then `scheduled`. When `publish_at` has already passed, the video is uploaded as public
  and the post is `published`.
- **Interrupted upload**: before uploading again a post whose upload may have reached
  YouTube, the platform looks among the 50 latest uploads of the channel for a video with
  the post's title, scheduled at `publish_at` or published after it, and takes it as the
  post's video.
- **Publication**: once `publish_at` is reached, a public video makes the post
  `published`; a video still scheduled is checked again on the next pass. A video removed
  from the channel, or no longer scheduled, rejects the post.
- **Refusals**: a refusal from YouTube, such as an unknown category, rejects the post.
  Exhausted quota, rate limits and server errors leave it `failed`, retried on later
  passes.

## State

`remote_id` holds the YouTube video identifier. While an upload may have reached
YouTube, `extra` carries `"uploading": true`, which tells the platform to look for the
video before uploading again.
