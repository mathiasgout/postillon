# Tests

```sh
uv run pytest
```

The tests reach no bucket and no platform: S3 calls go to an in-memory client
(`tests/fake_s3.py`), the service loop runs with a fake adapter, and the platform adapters
with fake API clients.
