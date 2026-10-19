# Configuration

The service reads `postillon.toml` in its working directory. A key can be overridden by an
environment variable named `POSTILLON_` then the key, nested keys joined by `__`
(`POSTILLON_POLL_SECONDS`, `POSTILLON_BUCKET__NAME`). Secrets never go in the file (see
`environment.md`).

```toml
data_dir = "data"
poll_seconds = 60
max_video_bytes = 1073741824

[bucket]
endpoint = "https://<account>.r2.cloudflarestorage.com"
access_key_id = "<key id>"
name = "postillon"

[projects.my-project.youtube.main]
handle = "@mychannel"
refresh_token_env = "MY_YOUTUBE_REFRESH_TOKEN"

[projects.my-project.instagram.main]
username = "mychannel"
access_token_env = "MY_INSTAGRAM_TOKEN"

[projects.my-project.tiktok.main]
handle = "@mychannel"
```

| Key | Default | Meaning |
| --- | --- | --- |
| `data_dir` | `data` | Holds the database `postillon.db`, the videos waiting for their platforms (`videos/`) and the renewed Instagram tokens. |
| `poll_seconds` | `60` | Interval between two passes of the worker. |
| `max_video_bytes` | 1 GiB | Largest video the API accepts. |
| `bucket.endpoint`, `bucket.access_key_id`, `bucket.name` | | The S3-compatible bucket (see `bucket.md`); its secret key comes from the environment. |
| `projects.<project>.<platform>.<account>` | | One account of a platform in a project, as posts name it in their `account` field. |

A project name follows `[a-z0-9-]+`, an account name `[a-z0-9_-]+`; account names are scoped
by project and platform. The settings of an account belong to its platform: see
`youtube.md`, `instagram.md` and `tiktok.md`. At least one project is required.

The processes refuse to start on an unknown key, a name outside its alphabet, a platform
postillon does not know, or an account setting its platform refuses.
