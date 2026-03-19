import hashlib
import uuid
from typing import BinaryIO

import boto3
from botocore.config import Config as BotoConfig

from app.config import settings


class FileStorageService:
    def __init__(self):
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            config=BotoConfig(signature_version="s3v4"),
        )
        self._bucket = settings.S3_BUCKET

    def upload(self, file_data: BinaryIO, original_filename: str, mime_type: str) -> tuple[str, str, int]:
        """Upload file. Returns (storage_key, sha256_hex, size_bytes)."""
        content = file_data.read()
        size = len(content)

        if size > settings.FILE_MAX_SIZE_BYTES:
            raise ValueError(f"File size {size} exceeds maximum {settings.FILE_MAX_SIZE_BYTES}")

        sha256 = hashlib.sha256(content).hexdigest()
        storage_key = f"{uuid.uuid4()}/{original_filename}"

        self._client.put_object(
            Bucket=self._bucket,
            Key=storage_key,
            Body=content,
            ContentType=mime_type,
        )

        return storage_key, sha256, size

    def download(self, storage_key: str) -> bytes:
        """Download file content."""
        response = self._client.get_object(Bucket=self._bucket, Key=storage_key)
        return response["Body"].read()

    def get_presigned_url(self, storage_key: str, expires_in: int = 3600) -> str:
        """Generate presigned download URL."""
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": storage_key},
            ExpiresIn=expires_in,
        )

    def delete(self, storage_key: str) -> None:
        """Delete file from storage."""
        self._client.delete_object(Bucket=self._bucket, Key=storage_key)


def get_file_storage() -> FileStorageService:
    return FileStorageService()
