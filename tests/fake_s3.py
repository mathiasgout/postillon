import hashlib

from botocore.exceptions import ClientError


class FakeS3:
    """An in-memory S3 client, limited to the calls postillon makes."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.writes: list[str] = []
        self.deletes: list[str] = []

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        with open(filename, "rb") as f:
            self.put_object(Bucket=bucket, Key=key, Body=f.read())

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.objects[(Bucket, Key)] = Body
        self.writes.append(Key)

    def get_object(self, Bucket, Key):
        return {"Body": _Body(self._get(Bucket, Key))}

    def download_file(self, bucket, key, filename):
        data = self._get(bucket, key)
        with open(filename, "wb") as f:
            f.write(data)

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)
        self.deletes.append(Key)

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://signed.example/{Params['Key']}?expires={ExpiresIn}"

    def get_paginator(self, operation):
        return _Paginator(self)

    def _get(self, bucket, key):
        if (bucket, key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return self.objects[(bucket, key)]


class _Body:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data


class _Paginator:
    def __init__(self, s3):
        self.s3 = s3

    def paginate(self, Bucket, Prefix):
        contents = [
            {"Key": key, "ETag": f'"{hashlib.md5(data).hexdigest()}"'}
            for (bucket, key), data in sorted(self.s3.objects.items())
            if bucket == Bucket and key.startswith(Prefix)
        ]
        yield {"Contents": contents} if contents else {}
