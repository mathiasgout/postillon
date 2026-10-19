# Tests

```sh
uv sync --all-extras
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
```

The tests reach no bucket and no platform: each runs on a fresh database migrated in a
temporary directory, the bucket is an in-memory fake, the worker steps posts with a fake
platform, and the platform clients talk to fake API clients. The CI runs the same commands
on every push and pull request.
