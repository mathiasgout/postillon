# Configuration

The service reads a TOML file, `postillon.toml` in the working directory by default. It
declares the projects the service serves and, under each project, the accounts of each
platform. Secrets never go in this file: they come from the environment (see
`environment.md` and each platform's document).

```toml
poll_seconds = 60

[projects.my-project.youtube.my-youtube]
handle = "@mychannel"

[projects.other-project.youtube.other-youtube]
handle = "@otherchannel"
```

| Key | Meaning |
| --- | --- |
| `poll_seconds` | Interval between two passes over the bucket, 60 by default. |
| `projects.<project>.<platform>.<account>` | One account of a platform in a project, named as posts name it in their `account` field. |

The settings of an account belong to its platform and are described by the platform's
document (see `youtube.md`). Account names are scoped by project: two projects may each
have an account named `main`.

The service refuses to start on an unknown key, a name outside its alphabet (see
`bucket.md`), a platform it does not know, or an account whose settings its platform
refuses.
