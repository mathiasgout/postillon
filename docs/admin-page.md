# Administration pages

`postillon api` serves the administration pages under `/admin/`, clients of the API (see
`api.md`); `/` redirects there.
Like the API, they have no authentication and are served on a trusted network only. Times
show in the browser's time zone; hovering one shows it in UTC.

| Page | Path |
| --- | --- |
| To schedule | `/admin/` |
| Publications | `/admin/publications.html` |
| An entry | `/admin/entry.html?project={project}&key={key}` |

The navigation counts the posts to schedule on every page.

## To schedule

The posts of a manual platform still `pending` before their publication time, the nearest
first. Each one shows:

- the video, to play or download, once the entry has received it;
- `publish_at` and the time left until it;
- the caption, with a button that copies it;
- **Mark scheduled**, which marks the post scheduled through the API once the operator has
  scheduled it on its platform; the API's refusal, if any, is shown above the list.

## Publications

The entries, one row each with one column per platform, grouped by day of publication: the
upcoming ones from the nearest, then a line at the present time, then the past ones from the
latest, 100 at a time. They are filtered by project and by post status. A row shows the
errors of its posts, and opens the entry's page.

A status reads by its mark as well as by its color:

| Status | Mark |
| --- | --- |
| `pending` | hollow circle |
| `in_progress` (sending) | half-filled circle |
| `scheduled` | square |
| `published` | filled circle |
| `failed` | triangle |
| `rejected` | cross |

## An entry

The video while the service holds it, then each post with its status, account,
`remote_id`, failures, error and the history of its statuses, and the manifest as received.
An `outdated` post shows the publication time it was sent with.
A post to schedule carries the same tools as on the first page.
