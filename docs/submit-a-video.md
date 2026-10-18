# Submit a video

A producer installs postillon without extras: the producer side depends on the S3 client
only, never on a platform SDK.

```sh
uv add postillon
```

Set the bucket variables (see `environment.md`), for instance in a `.env` file of the
working directory, ignored by git:

```sh
POSTILLON_S3_ENDPOINT=https://<account>.r2.cloudflarestorage.com
POSTILLON_S3_ACCESS_KEY_ID=...
POSTILLON_S3_SECRET_ACCESS_KEY=...
POSTILLON_BUCKET=my-bucket
```

## Submit an entry

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
        posts=[YouTube(
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
`ValueError` on an invalid entry or a video that is not an MP4 file, before writing
anything.

`publish_at` accepts any time zone and is stored in UTC: `datetime(2026, 10, 19, 8, 0,
tzinfo=ZoneInfo("Europe/Paris"))` is the same publication time.

## Set the platform options

Each post carries the options of its platform, with their defaults (see `youtube.md`,
`instagram.md`). An entry holds one post per platform it publishes on:

```python
from postillon.platforms.instagram import Instagram

posts = [
    YouTube(
        account="my-youtube",
        title="Pasta in ten minutes",
        description="A quick weeknight recipe.\n#cooking #pasta",
        category_id="26",
        contains_synthetic_media=True,
    ),
    Instagram(
        account="my-instagram",
        caption="Pasta in ten minutes.\n#cooking #pasta",
        thumb_offset=1500,
    ),
]
```

## Submit a series

An entry identifier may hold `/`, which groups the entries of a series under one prefix.
A week of videos, one a day at 6 a.m. UTC:

```python
from datetime import timedelta

first = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
for day, video in enumerate(sorted(Path("week-43").glob("*.mp4"))):
    bucket.submit(
        Entry(
            id=f"week-43/{video.stem}",
            publish_at=first + timedelta(days=day),
            posts=[YouTube(account="my-youtube", title=video.stem.replace("-", " ").capitalize())],
        ),
        video=video,
    )
```

## Change a publication

Submit the entry again under the same `id`, with its new values: the new manifest replaces
the old one, and the service applies it to the posts it has not sent to their platform yet
(see `state.md`). Moving a publication one hour later:

```python
bucket.submit(
    Entry(
        id="pasta-in-ten-minutes",
        publish_at=datetime(2026, 10, 19, 7, 0, tzinfo=UTC),
        posts=[YouTube(account="my-youtube", title="Pasta in ten minutes")],
    ),
    video=Path("pasta.mp4"),
)
```

## Handle a refusal

```python
try:
    bucket.submit(entry, video=Path("pasta.mp4"))
except ValueError as e:
    print(f"{entry.id} not submitted: {e}")
```

The message names the rule that fails, such as `youtube: title is 112 characters, limit
100`. Nothing is written, so the same call can be repeated once the entry is fixed.
