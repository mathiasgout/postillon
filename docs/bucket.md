# Bucket

The service keeps two things in one S3-compatible bucket (Cloudflare R2), and is its only
writer. Producers never reach it.

```
<project>/videos/<key>.mp4         a video a platform fetches by signed URL
_postillon/backups/<date>.sqlite3  a daily copy of the database
```

- **Videos**: the service copies a video to the bucket when a platform asks for a URL,
  Instagram for a Reel, and deletes it once every platform holds the video (see
  `statuses.md`). A signed URL reads the video without credentials until it expires.
- **Backups**: the worker uploads a consistent copy of the database on its first pass of
  each day, in UTC, and after each start; a failed backup is tried again after the next
  pass. The prefix lies outside the project alphabet, so that no project can collide
  with it. postillon deletes no backup. Without a backup, a lost disk would make the
  service forget the posts in progress and send again a video a platform already holds.

The credentials need read, write and delete access to this bucket only (see
`configuration.md` and `environment.md`).
