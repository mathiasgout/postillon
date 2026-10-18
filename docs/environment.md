# Environment

Both sides reach the bucket with the same variables. The service needs more for the
platforms, described by each platform's document.

| Variable | Role |
| --- | --- |
| `POSTILLON_S3_ENDPOINT` | Endpoint URL of the S3-compatible storage, `https://<account>.r2.cloudflarestorage.com` on R2. |
| `POSTILLON_S3_ACCESS_KEY_ID` | Access key of an API token with read and write access to the bucket. |
| `POSTILLON_S3_SECRET_ACCESS_KEY` | Secret of that access key. |
| `POSTILLON_BUCKET` | Bucket name. |

The variables are read from the process environment, and from a `.env` file found from
the working directory upwards; a variable set in the process wins. `postillon login`
writes the secrets it obtains to that file, or creates `.env` in the working directory,
readable by its owner only.
