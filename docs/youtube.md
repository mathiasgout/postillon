# YouTube

The YouTube adapter uploads the video as private with a scheduled publication time
(`publishAt`), so that YouTube publishes it at `publish_at` by itself. It acts as soon as
it discovers the manifest, and updates the scheduled video when the manifest changes.

## Post

```json
"youtube": {
  "account": "my-youtube",
  "title": "Pasta in ten minutes",
  "description": "A quick weeknight recipe.\n#cooking #pasta",
  "category_id": "26",
  "made_for_kids": false,
  "contains_synthetic_media": false
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `account` | yes | Account identifier, declared under the project in the service configuration; it designates one YouTube channel. |
| `title` | yes | Video title, 100 characters at most, without `<` or `>`. |
| `description` | no | Video description, 5000 bytes at most, without `<` or `>`. Empty by default. |
| `category_id` | no | YouTube category, `"22"` (People & Blogs) by default. |
| `made_for_kids` | no | Audience declaration, `false` by default. |
| `contains_synthetic_media` | no | Altered or synthetic content declaration, `false` by default. |
| `video_id` | no | A video already uploaded to the channel, adopted instead of a new upload. |

An adopted video is not uploaded again: the service sets its title, description and
`publishAt` from the manifest and records it as `scheduled`.

A manifest change updates the title, description, category and `publishAt` of a
scheduled video. YouTube does not replace the file of an uploaded video: a new video
submitted for the same entry has no effect on YouTube.

## State

`remote_id` holds the YouTube video identifier. The adapter adds no other field.
