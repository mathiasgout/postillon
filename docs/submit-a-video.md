# Submit a video

A producer installs postillon without extras: the producer side depends on the S3 client
only, never on a platform SDK.

```sh
uv add postillon
```

Set the bucket variables (see `environment.md`), then submit each entry:

```python
from datetime import UTC, datetime
from pathlib import Path

from postillon import Bucket, Entry
from postillon.platforms.youtube import YouTube

bucket = Bucket.from_env(project="my-project")
bucket.submit(
    Entry(
        id="pasta-in-ten-minutes",
        publish_at=datetime(2026, 10, 19, 6, 0, tzinfo=UTC),
        platforms=[YouTube(
            account="my-youtube",
            title="Pasta in ten minutes",
            description="A quick weeknight recipe.",
        )],
    ),
    video=Path("pasta.mp4"),
)
```

`submit` validates the entry (see `manifest.md`), uploads the video, then writes the
manifest, so that the service never sees a manifest without its video. It raises
`ValueError` on an invalid entry, before writing anything.

To change a publication, submit the entry again under the same `id`: the new manifest
replaces the old one, and the service applies it to the platforms that have not
published yet (see `state.md`).
