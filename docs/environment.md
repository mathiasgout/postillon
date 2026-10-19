# Environment

Secrets come from environment variables, completed by the `.env` file of the working
directory, which never overrides a variable already set. postillon never writes `.env`.

| Variable | Meaning |
| --- | --- |
| `POSTILLON_BUCKET__SECRET_ACCESS_KEY` | Secret key of the bucket's credentials. |
| `POSTILLON_YOUTUBE_CLIENT_ID`, `POSTILLON_YOUTUBE_CLIENT_SECRET` | The OAuth client of the YouTube accounts, unless an account names its own (see `youtube.md`). |
| The variable each account names | Its refresh token (`refresh_token_env`, see `youtube.md`) or access token (`access_token_env`, see `instagram.md`). |

Any key of `postillon.toml` can also be set here (see `configuration.md`).
