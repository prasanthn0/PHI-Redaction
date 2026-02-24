"""File storage management for outputs and validation (PDF + image files)."""

import logging
import re
import uuid
from pathlib import Path
from typing import Optional

import filetype
import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)


PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf", "binary/octet-stream", "application/octet-stream"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif"}
ALLOWED_EXTENSIONS = {".pdf"} | IMAGE_EXTENSIONS


class FileStorage:
    """Manages file storage for outputs and file validation."""

    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize file storage.

        Args:
            base_dir: Base directory for storage. Uses settings if not provided.
        """
        self._base_dir = base_dir

    @property
    def base_dir(self) -> Path:
        """Get the base storage directory."""
        if self._base_dir is None:
            settings = get_settings()
            self._base_dir = settings.storage_dir
        return self._base_dir

    @property
    def outputs_dir(self) -> Path:
        """Get the outputs directory."""
        path = self.base_dir / "outputs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def downloads_dir(self) -> Path:
        """Get the downloads directory for URL-fetched files."""
        path = self.base_dir / "downloads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _convert_gdrive_url(url: str) -> str:
        """Convert a Google Drive share link to a direct download URL."""
        match = re.search(r"drive\.google\.com/file/d/([^/]+)", url)
        if match:
            file_id = match.group(1)
            return f"https://drive.google.com/uc?export=download&id={file_id}"
        return url

    async def download_url_to_storage(self, url: str, file_id: str) -> Path:
        """
        Download a PDF from a URL into local storage.

        Args:
            url: HTTP(S) URL to download.
            file_id: Unique identifier used for the local filename.

        Returns:
            Path to the downloaded file.

        Raises:
            ValueError: If the download fails or exceeds size limits.
        """
        settings = get_settings()
        max_bytes = settings.max_file_size_bytes
        dest = self.downloads_dir / f"{file_id}.pdf"

        download_url = self._convert_gdrive_url(url)
        logger.info("Downloading URL %s (resolved: %s) -> %s", url, download_url, dest)

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
                async with client.stream("GET", download_url) as response:
                    response.raise_for_status()

                    # Check Content-Type header
                    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                    if content_type and content_type not in PDF_CONTENT_TYPES:
                        raise ValueError(
                            f"URL did not return a PDF (Content-Type: {content_type}): {url}"
                        )

                    downloaded = 0
                    oversized = False
                    with open(dest, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            downloaded += len(chunk)
                            if downloaded > max_bytes:
                                oversized = True
                                break
                            f.write(chunk)
                    if oversized:
                        dest.unlink(missing_ok=True)
                        raise ValueError(
                            f"Download exceeds maximum allowed size of {settings.max_file_size_mb}MB."
                        )
        except httpx.HTTPStatusError as e:
            dest.unlink(missing_ok=True)
            raise ValueError(f"Failed to download URL (HTTP {e.response.status_code}): {url}") from e
        except httpx.HTTPError as e:
            dest.unlink(missing_ok=True)
            raise ValueError(f"Failed to download URL: {e}") from e

        # Verify PDF magic bytes
        self._verify_pdf_content(dest, source=url)

        logger.info("Downloaded %d bytes to %s", downloaded, dest)
        return dest

    async def upload_file_to_url(self, local_path: Path, upload_url: str) -> None:
        """
        Upload a local file to a remote URL via HTTP PUT.

        Supports Azure Blob SAS URLs and S3 presigned URLs.

        Args:
            local_path: Path to the local file to upload.
            upload_url: Presigned/SAS URL to PUT the file to.

        Raises:
            ValueError: If the upload fails.
        """
        safe_url = upload_url.split("?")[0]
        logger.info("Uploading %s to %s", local_path, safe_url)

        data = local_path.read_bytes()
        headers = {"Content-Type": "application/pdf"}

        if ".blob.core.windows.net" in upload_url:
            headers["x-ms-blob-type"] = "BlockBlob"

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.put(upload_url, content=data, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"Failed to upload to URL (HTTP {e.response.status_code}): {safe_url}"
            ) from e
        except httpx.HTTPError as e:
            raise ValueError(f"Failed to upload to URL: {safe_url}: {e}") from e

        logger.info("Uploaded %d bytes to %s", len(data), safe_url)

    @staticmethod
    def _verify_pdf_content(path: Path, source: str = "") -> None:
        """Verify that a file is a valid PDF using MIME type detection."""
        kind = filetype.guess(path)
        label = source or str(path)
        if kind is None:
            raise ValueError(f"File type could not be determined: {label}")
        if kind.mime != "application/pdf":
            raise ValueError(f"File is not a valid PDF (detected: {kind.mime}): {label}")

    def validate_file_path(self, file_path: str) -> Path:
        """
        Validate that a file path points to an existing PDF within size limits.

        Args:
            file_path: Path to validate

        Returns:
            Resolved Path object

        Raises:
            ValueError: If validation fails
        """
        path = Path(file_path)

        if not path.exists():
            raise ValueError(f"File not found: {file_path}")

        if not path.is_file():
            raise ValueError(f"Not a file: {file_path}")

        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {path.suffix}. Allowed: PDF, JPEG, PNG, TIFF")

        if path.suffix.lower() == ".pdf":
            self._verify_pdf_content(path)

        settings = get_settings()
        file_size = path.stat().st_size
        if file_size > settings.max_file_size_bytes:
            raise ValueError(
                f"File size ({file_size} bytes) exceeds maximum allowed size of {settings.max_file_size_mb}MB."
            )

        return path

    def get_output_paths(self, job_id: str) -> tuple[Path, Path]:
        """
        Get output paths for a job.

        Args:
            job_id: The job ID

        Returns:
            Tuple of (output_pdf_path, metadata_json_path)
        """
        output_pdf = self.outputs_dir / f"{job_id}_redacted.pdf"
        metadata_json = self.outputs_dir / f"{job_id}_metadata.json"
        return output_pdf, metadata_json

    def file_exists(self, file_path: Path) -> bool:
        """Check if a file exists."""
        return file_path.exists()

    def delete_file(self, file_path: Path) -> bool:
        """Delete a file. Returns True if deleted, False if not found."""
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def cleanup_job_files(self, job_id: str, input_path: Optional[Path] = None) -> None:
        """
        Clean up all files associated with a job.

        Args:
            job_id: The job ID
            input_path: Optional input file path to also delete
        """
        output_pdf, metadata_json = self.get_output_paths(job_id)
        self.delete_file(output_pdf)
        self.delete_file(metadata_json)

        if input_path:
            self.delete_file(input_path)


# Global file storage instance
file_storage = FileStorage()
