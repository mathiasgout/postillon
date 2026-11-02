# Run the service

The service is two processes sharing one SQLite database: `postillon api` serves the API,
`postillon worker` publishes. Both run from a working directory that holds `postillon.toml`
(see `configuration.md`), the `.env` of the secrets (see `environment.md`) and `data_dir`.

```sh
uv tool install 'postillon[youtube,instagram]'
cd /opt/postillon
postillon migrate
postillon api --host 0.0.0.0
postillon worker
```

| Command | Purpose |
| --- | --- |
| `postillon migrate` | Brings the database schema to the latest version; run after every install or upgrade. |
| `postillon api [--host 127.0.0.1] [--port 8000]` | Serves the API (see `api.md`); `--host 0.0.0.0` serves the local network. |
| `postillon worker` | Runs a pass every `poll_seconds` (see `statuses.md`). Once a day, it backs the database up to the bucket (see `bucket.md`) and checks the credentials that expire (see `instagram.md`). |

Both processes refuse to start, with exit status 2, on an invalid configuration, a missing
secret or platform extra, or a database whose schema is not current. They log to standard
error: each status change of a post, failures, and the daily jobs.

## Stopping

The worker stops after its current pass on SIGTERM or Ctrl-C. A pass cut short leaves
`in_progress` posts, which their platform resolves on the next start (see `statuses.md`).

## As systemd services

```ini
# /etc/systemd/system/postillon-api.service
[Unit]
Description=postillon API
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/postillon
ExecStartPre=/home/postillon/.local/bin/postillon migrate
ExecStart=/home/postillon/.local/bin/postillon api --host 0.0.0.0
Restart=on-failure
User=postillon

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/postillon-worker.service
[Unit]
Description=postillon worker
After=postillon-api.service
Wants=network-online.target

[Service]
WorkingDirectory=/opt/postillon
ExecStart=/home/postillon/.local/bin/postillon worker
Restart=on-failure
# A pass may be uploading a video: leave it time to end before SIGKILL.
TimeoutStopSec=600
User=postillon

[Install]
WantedBy=multi-user.target
```
