# Bucket layout

Producers and the service exchange nothing but objects in one S3-compatible bucket
(Cloudflare R2). The bucket holds several projects side by side, one prefix each, and
every object has exactly one writer.

```
<project>/manifests/<entry>.json   written by the producer, read by the service
<project>/videos/<entry>.mp4       written by the producer, read then deleted by the service
<project>/states/<entry>.json      written and read by the service only
```

A producer writes under its own project prefix and never reads anything back. The service
lists the prefixes of the projects declared in its configuration and ignores the others.

## Names

- **Project**: lowercase letters, digits and `-`.
- **Entry**: one video to publish on one or more platforms. Lowercase letters, digits,
  `-`, `_` and `/`; unique within its project and never reused, even after publication.

## Lifecycle

1. The producer submits the entry: the video first, then the manifest, so that a
   discovered manifest always finds its video (see `submit-a-video.md`).
2. The service lists each project's `manifests/` at a fixed interval. It reads a manifest
   when it is new or its ETag changed, and hands every post that needs work to its
   platform's adapter (see `state.md`).
3. To change a publication, the producer submits the entry again. The service applies the
   change on the posts that have not published yet (see `state.md`).
4. Once every post of the entry is `scheduled` or `published`, its platform holds the
   video and the service deletes the bucket copy. A bucket lifecycle rule removes the
   manifest and the state later; the service forgets an entry whose manifest is gone.
