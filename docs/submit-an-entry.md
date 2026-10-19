# Submit an entry

An entry is one video to publish on one or more platforms. A producer submits it with one
`PUT` to the API (see `api.md`): the manifest as JSON (see `manifest.md`) and the MP4 video,
as `multipart/form-data`.

```sh
curl -X PUT http://localhost:8000/v1/projects/my-project/entries/season-1/day-23 \
  -F 'entry=<day-23.json' \
  -F 'video=@day-23.mp4;type=video/mp4'
```

```python
import json

import httpx

manifest = {
    "publish_at": "2026-10-22T18:00:00Z",
    "posts": {
        "youtube": {"account": "main", "title": "Pasta in ten minutes"},
        "instagram": {"account": "main", "caption": "Pasta in ten minutes #cooking"},
    },
}
with open("day-23.mp4", "rb") as video:
    response = httpx.put(
        "http://localhost:8000/v1/projects/my-project/entries/season-1/day-23",
        data={"entry": json.dumps(manifest)},
        files={"video": ("day-23.mp4", video, "video/mp4")},
        timeout=300,
    )
response.raise_for_status()
```

The key, `season-1/day-23` here, is chosen by the producer and never reused within its
project. Submitting the same key again replaces the entry; the video may then be left out
while the service holds it.

## The answer

- **201 or 200**: the entry is created or replaced. `ignored` lists the platforms whose
  post may have reached its platform already and stays as it was sent.
- **422**: the entry is refused, with the reason in `detail`; nothing is written.
- **409**: the worker changed a post of the entry meanwhile; submitting again settles it.

The state of each post is then read with `GET` on the same address (see `statuses.md`).
