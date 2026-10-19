# Administration page

`postillon api` serves the administration page at `/`, a client of the API (see `api.md`).
Like the API, it has no authentication and is served on a trusted network only.

## To schedule

The posts of a manual platform still `pending` before their publication time, the nearest
first. Each one shows:

- the video, to play or download, while the service holds it;
- the caption, with a button that copies it;
- `publish_at`, in the browser's time zone, and the time left until it;
- **Mark scheduled**, which marks the post scheduled through the API once the operator has
  scheduled it on its platform; the API's refusal, if any, is shown at the top of the page.

## Entries

The entries, latest publication time first, 50 at a time, filtered by project and by post
status. Each entry shows its publication time, its submissions, whether the service still
holds the video, and each post with its status, account, `remote_id`, failures, error and
the history of its statuses.

Times show in the browser's time zone; hovering one shows it in UTC.
