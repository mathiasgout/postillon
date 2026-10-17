# postillon

postillon publishes videos to their platforms, each at its scheduled time, from entries
that producers drop in an S3-compatible bucket. One package, two sides: producers submit
entries through its Python API, and its service reads them and talks to the platforms.

A producer only writes to the bucket and never reads from it; the service alone holds
the platform credentials.

## Documentation

- `docs/submit-a-video.md`: install postillon on the producer side and submit an entry.
- `docs/environment.md`: the variables both sides use to reach the bucket.
- `docs/run-the-service.md`: install and run the service, as a command or a systemd service.
- `docs/configuration.md`: the projects and accounts the service serves.
- `docs/bucket.md`: how projects, manifests, videos and states are laid out, and the
  lifecycle of an entry.
- `docs/manifest.md`: the manifest of an entry, its fields and its validation.
- `docs/state.md`: the state the service keeps per entry, its statuses and how manifest
  changes show.
- `docs/youtube.md`: the YouTube platform, its post and its state.
- `docs/add-a-platform.md`: the post and the adapter a new platform provides.
- `docs/tests.md`: run the tests.
