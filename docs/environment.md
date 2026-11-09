# Environment

Secrets come from environment variables, completed by the `.env` file next to the
configuration file (see `configuration.md`), which never overrides a variable already set. postillon never writes `.env`.

| Variable | Meaning |
| --- | --- |
| `POSTILLON_BUCKET__SECRET_ACCESS_KEY` | Secret key of the bucket's credentials. |
| `POSTILLON_YOUTUBE_CLIENT_ID`, `POSTILLON_YOUTUBE_CLIENT_SECRET` | The OAuth client of the YouTube accounts, unless an account names its own (see `youtube.md`). |
| The variable each account names | Its refresh token (`refresh_token_env`, see `youtube.md`) or Page access token (`access_token_env`, see `instagram.md`). |

Any key of the configuration file can also be set here (see `configuration.md`).
