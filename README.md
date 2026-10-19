# postillon

postillon publishes videos to their platforms (YouTube, Instagram, TikTok), each at its time. Producers
submit entries to its HTTP API, a video with one post per platform; its worker publishes them,
or follows the operator who schedules them on a manual platform, and records every status in a
SQLite database.

A post that may have reached its platform is never modified: a new submission changes only
the posts not sent yet.

## Documentation

- `docs/submit-an-entry.md`: submit an entry from a producer.
- `docs/api.md`: the routes of the API, their bodies and their errors.
- `docs/manifest.md`: the manifest of an entry, its fields and its validation.
- `docs/statuses.md`: the statuses of a post, when the worker steps it, and when the video goes.
- `docs/youtube.md`: the YouTube platform, its accounts, its post and its behavior.
- `docs/instagram.md`: the Instagram platform, its accounts and their tokens, its post and its behavior.
- `docs/tiktok.md`: the TikTok platform, scheduled by the operator, its accounts, its post and its behavior.
- `docs/run-the-service.md`: install, migrate and run the API and the worker, under systemd.
- `docs/configuration.md`: `postillon.toml`, the projects and their accounts.
- `docs/environment.md`: the environment variables, secrets included.
- `docs/bucket.md`: what the service keeps in its S3-compatible bucket.
- `docs/add-a-platform.md`: the post, the account settings and the client a new platform provides.
- `docs/tests.md`: run the tests, the lint and the type checks.
