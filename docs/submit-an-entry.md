# Submit an entry

An entry is one video to publish on one or more platforms. A producer submits it in two
requests to the API (see `api.md`): the manifest first, as JSON (see `manifest.md`), then
the MP4 video. The entry exists from the manifest on; its posts wait for the video.

```sh
curl -X PUT http://localhost:8000/v1/projects/my-project/entries/day-23 \
  -H 'Content-Type: application/json' --data @day-23.json
curl -X PUT http://localhost:8000/v1/projects/my-project/entries/day-23/video \
  -H 'Content-Type: video/mp4' --data-binary @day-23.mp4
```

```python
import httpx

entry = "http://localhost:8000/v1/projects/my-project/entries/day-23"
manifest = {
    "publish_at": "2026-10-22T18:00:00Z",
    "posts": {
        "youtube": {"account": "main", "title": "Pasta in ten minutes"},
        "instagram": {"account": "main", "caption": "Pasta in ten minutes #cooking"},
    },
}
httpx.put(entry, json=manifest).raise_for_status()
with open("day-23.mp4", "rb") as video:
    httpx.put(f"{entry}/video", content=video, headers={"Content-Type": "video/mp4"}, timeout=300).raise_for_status()
```

The key, `day-23` here, is chosen by the producer and never reused within its project.
Submitting the same key again replaces the manifest; the video is sent again only when it
changes, and sending the same bytes changes nothing.

## The answers

- **201 or 200** for the manifest, **201 or 204** for the video: the entry or its video is
  created or replaced. A post that may have reached its platform keeps what it was sent
  with, and says so by `outdated`.
- **4xx**: the request is refused, with its `type` and `detail` (see `api.md`); nothing is
  written.
- **409** `changed-meanwhile`: the worker changed the entry meanwhile; sending again
  settles it.

To create an entry without ever replacing one, send the manifest with
`If-None-Match: *`, which answers `412` when the key exists. The state of each post is then
read with `GET` on the entry (see `statuses.md`).
