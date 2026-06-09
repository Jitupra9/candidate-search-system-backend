# app/services/s3_processor.py
"""
Production-grade S3 download + process utility.
Used by Celery workers — fully synchronous (boto3, not aioboto3).

Responsibilities:
  - Download file from S3 to a secure temp file
  - Validate file integrity after download
  - Provide a context manager for safe temp file cleanup
  - Never leave temp files on disk even if processing crashes
"""
from __future__ import annotations
from pathlib import Path
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Retry config for transient S3 network errors
_BOTO_CONFIG = Config(
    retries={
        "max_attempts": 3,
        "mode": "adaptive",   # backs off on throttling
    },
    connect_timeout=10,
    read_timeout=60,          # large files need more time
)


# ─── S3 Client ────────────────────────────────────────────────────────────────

def _get_s3_client():

    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        raise EnvironmentError(
            "AWS credentials not configured. "
            "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env"
        )

    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=_BOTO_CONFIG,
    )


# ─── URL → Key ────────────────────────────────────────────────────────────────

def extract_s3_key(s3_url: str) -> str:

    if not s3_url or not s3_url.startswith("http"):
        raise ValueError(f"Invalid S3 URL: {s3_url!r}")

    parsed = urlparse(s3_url)
    path = parsed.path.lstrip("/")

    # Virtual-hosted style — bucket name is part of hostname
    if settings.AWS_S3_BUCKET in parsed.netloc:
        key = path
    else:
        parts = path.split("/", 1)
        if len(parts) != 2 or parts[0] != settings.AWS_S3_BUCKET:
            raise ValueError(
                f"S3 URL bucket mismatch. "
                f"Expected '{settings.AWS_S3_BUCKET}', got URL: {s3_url}"
            )
        key = parts[1]

    if not key:
        raise ValueError(f"Could not extract object key from S3 URL: {s3_url}")

    return key


def _get_file_extension(s3_url: str) -> str:
    """
    Derive file extension from S3 URL.
    Strips query params first (presigned URLs have ?X-Amz-... params).
    Falls back to .tmp if unknown.
    """
    clean_url = s3_url.split("?")[0]
    ext = Path(clean_url).suffix.lower()
    return ext if ext in {".pdf", ".txt", ".doc", ".docx"} else ".tmp"


# ─── S3 File Metadata ─────────────────────────────────────────────────────────

def get_s3_object_metadata(s3_url: str) -> dict:
    key = extract_s3_key(s3_url)
    client = _get_s3_client()

    try:
        response = client.head_object(Bucket=settings.AWS_S3_BUCKET, Key=key)
        return {
            "size_bytes": response.get("ContentLength", 0),
            "content_type": response.get("ContentType", ""),
            "etag": response.get("ETag", "").strip('"'),
            "last_modified": response.get("LastModified"),
        }
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("404", "NoSuchKey"):
            raise FileNotFoundError(f"File not found in S3: {key}")
        if code == "403":
            raise PermissionError(f"Access denied to S3 object: {key}")
        raise RuntimeError(f"S3 metadata check failed [{code}]: {exc}") from exc


# ─── Core Download ────────────────────────────────────────────────────────────

def download_from_s3(s3_url: str, dest_path: str) -> int:
    key = extract_s3_key(s3_url)
    client = _get_s3_client()

    logger.info(
        "s3_download.started",
        key=key,
        dest=dest_path,
        bucket=settings.AWS_S3_BUCKET,
    )

    try:
        client.download_file(
            Bucket=settings.AWS_S3_BUCKET,
            Key=key,
            Filename=dest_path,
        )
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("404", "NoSuchKey"):
            raise FileNotFoundError(f"S3 object not found: {key}") from exc
        if code == "403":
            raise PermissionError(f"Access denied to S3 object: {key}") from exc
        raise RuntimeError(f"S3 download failed [{code}]: {exc}") from exc
    except NoCredentialsError as exc:
        raise EnvironmentError("AWS credentials missing or expired.") from exc

    # Verify the file actually landed and has content
    size = os.path.getsize(dest_path)
    if size == 0:
        os.unlink(dest_path)
        raise ValueError(f"Downloaded file is empty: {key}")

    logger.info("s3_download.completed", key=key, size_bytes=size)
    return size


# ─── Context Manager — Safe Temp File ────────────────────────────────────────

@contextmanager
def s3_file_as_temp(s3_url: str) -> Generator[Path, None, None]:
    ext = _get_file_extension(s3_url)
    tmp_file = tempfile.NamedTemporaryFile(
        suffix=ext,
        prefix="rag_s3_",
        dir=tempfile.gettempdir(),
        delete=False,       # we manage deletion ourselves
    )
    tmp_path = Path(tmp_file.name)
    tmp_file.close()        # close handle so boto3 can write to it

    logger.info("s3_temp.created", path=str(tmp_path), s3_url=s3_url[:80])

    try:
        # ── Pre-flight: check file size before downloading ────────
        try:
            meta = get_s3_object_metadata(s3_url)
            max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
            if meta["size_bytes"] > max_bytes:
                raise ValueError(
                    f"File too large: {meta['size_bytes'] / 1024 / 1024:.1f} MB "
                    f"(max {settings.MAX_FILE_SIZE_MB} MB)"
                )
        except (FileNotFoundError, PermissionError):
            raise
        except Exception as exc:
            # metadata check failure is non-fatal — proceed with download
            logger.warning("s3_temp.metadata_check_failed", error=str(exc))

        # ── Download ──────────────────────────────────────────────
        download_from_s3(s3_url, str(tmp_path))

        # Yield the path to the caller (Celery task)
        yield tmp_path

    finally:
        # ── Guaranteed cleanup ────────────────────────────────────
        if tmp_path.exists():
            try:
                tmp_path.unlink()
                logger.info("s3_temp.cleaned", path=str(tmp_path))
            except OSError as exc:
                # Log but don't raise — cleanup failure shouldn't
                # mask the original processing error
                logger.error(
                    "s3_temp.cleanup_failed",
                    path=str(tmp_path),
                    error=str(exc),
                )


# ─── High-Level: Download + Extract Text ──────────────────────────────────────



def download_and_extract_text(s3_url: str) -> dict:

    from app.services.file_service import FileServices

    metadata = get_s3_object_metadata(s3_url)

    with s3_file_as_temp(s3_url) as tmp_path:
        text = FileServices.extract_text_from_pdf(tmp_path)

        return {
            "file_name": Path(s3_url.split("?")[0]).name,
            "file_type": tmp_path.suffix.lower(),
            "file_size": metadata["size_bytes"],
            "content_type": metadata["content_type"],
            "page_count": metadata.get("page_count", 0),
            "content": text,
        }
    
