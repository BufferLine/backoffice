import hashlib
import re
import uuid
from typing import BinaryIO

import boto3
from botocore.config import Config as BotoConfig

from app.config import settings


def safe_filename(name: str) -> str:
    """Sanitize filename for use in Content-Disposition headers."""
    return re.sub(r'[^\w\-.]', '_', name)


ALLOWED_MIME_TYPES = {
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
    "application/pdf",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}


class FileStorageService:
    def __init__(self):
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            config=BotoConfig(signature_version="s3v4"),
        )
        self._bucket = settings.S3_BUCKET

    def upload(self, file_data: BinaryIO, original_filename: str, mime_type: str) -> tuple[str, str, int]:
        """Upload file. Returns (storage_key, sha256_hex, size_bytes)."""
        if mime_type not in ALLOWED_MIME_TYPES:
            raise ValueError(f"File type '{mime_type}' is not allowed")

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
