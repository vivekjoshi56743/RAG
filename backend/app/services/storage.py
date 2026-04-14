"""
Google Cloud Storage helpers for uploading, downloading, and generating
signed URLs for original document files.
"""
from google.cloud import storage
from app.config import settings

_client: storage.Client | None = None


def get_gcs_client() -> storage.Client:
    global _client
    if _client is None:
        _client = storage.Client()
    return _client


def get_bucket() -> storage.Bucket:
    return get_gcs_client().bucket(settings.gcs_bucket)


def upload_file(file_bytes: bytes, destination_path: str, content_type: str = "application/octet-stream") -> str:
    """Upload bytes to GCS and return the GCS path (not a URL)."""
    blob = get_bucket().blob(destination_path)
    blob.upload_from_string(file_bytes, content_type=content_type)
    return destination_path


def download_file(gcs_path: str) -> bytes:
    """Download a file from GCS and return its bytes."""
    blob = get_bucket().blob(gcs_path)
    return blob.download_as_bytes()


def generate_signed_url(gcs_path: str, expiration_seconds: int = 3600) -> str:
    """Generate a signed URL for temporary direct access (e.g. PDF viewer)."""
    import datetime
    blob = get_bucket().blob(gcs_path)
    return blob.generate_signed_url(
        expiration=datetime.timedelta(seconds=expiration_seconds),
        method="GET",
    )


def delete_file(gcs_path: str) -> None:
    """Delete a file from GCS."""
    blob = get_bucket().blob(gcs_path)
    blob.delete()
