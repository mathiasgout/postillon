# Run the service

Install postillon with the extras of the platforms the configuration uses:

```sh
uv tool install 'postillon[youtube,instagram]'
```

Set the bucket variables and the platforms' secrets (see `environment.md`), write the
configuration (see `configuration.md`), then start the service from that directory:

```sh
postillon serve
```

| Option | Meaning |
| --- | --- |
| `--config <path>` | Configuration file, `postillon.toml` by default. |
| `--once` | Run a single pass, then exit. |

## Logs and exit

The service logs each status change of a post, rejected manifests and failures to
standard error. It exits with status 2 when the configuration, a variable or a
platform's extra is missing, and runs until stopped otherwise.

## As a systemd service

```ini
[Unit]
Description=postillon
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/postillon
ExecStart=/home/postillon/.local/bin/postillon serve
Restart=on-failure
User=postillon

[Install]
WantedBy=multi-user.target
```

`WorkingDirectory` holds `postillon.toml`, the `.env` with the secrets, and the files the
service writes, such as `instagram-tokens.json` (see `instagram.md`). Stopping the
service during an upload is safe: the post stays `in_progress`, and its adapter resolves
it on the next start (see `state.md`).
