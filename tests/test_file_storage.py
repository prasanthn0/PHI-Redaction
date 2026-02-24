"""Unit tests for FileStorage: URL conversion, MIME validation, and download logic."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.storage.file_storage import FileStorage


class TestConvertGdriveUrl:
    def test_share_link_converted_to_direct_download(self):
        url = "https://drive.google.com/file/d/1aBcDeFgHiJkLmNo/view?usp=sharing"
        result = FileStorage._convert_gdrive_url(url)
        assert result == "https://drive.google.com/uc?export=download&id=1aBcDeFgHiJkLmNo"

    def test_share_link_without_query_params(self):
        url = "https://drive.google.com/file/d/ABCDEF123456/view"
        result = FileStorage._convert_gdrive_url(url)
        assert result == "https://drive.google.com/uc?export=download&id=ABCDEF123456"

    def test_non_gdrive_url_returned_unchanged(self):
        url = "https://example.com/documents/report.pdf"
        result = FileStorage._convert_gdrive_url(url)
        assert result == url

    def test_gdrive_url_without_file_path_returned_unchanged(self):
        url = "https://drive.google.com/drive/folders/someFolder"
        result = FileStorage._convert_gdrive_url(url)
        assert result == url


class TestVerifyPdfContent:
    def test_valid_pdf_passes(self, tmp_path):
        pdf_file = tmp_path / "valid.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")
        FileStorage._verify_pdf_content(pdf_file)

    def test_text_file_with_pdf_extension_rejected(self, tmp_path):
        fake_pdf = tmp_path / "fake.pdf"
        fake_pdf.write_text("This is not a PDF, just plain text content.")
        with pytest.raises(ValueError, match="not a valid PDF|could not be determined"):
            FileStorage._verify_pdf_content(fake_pdf)

    def test_html_file_with_pdf_extension_rejected(self, tmp_path):
        fake_pdf = tmp_path / "gdrive_error.pdf"
        fake_pdf.write_text("<html><body><h1>Google Drive - Virus scan warning</h1></body></html>")
        with pytest.raises(ValueError, match="not a valid PDF|could not be determined"):
            FileStorage._verify_pdf_content(fake_pdf)

    def test_png_file_with_pdf_extension_rejected(self, tmp_path):
        fake_pdf = tmp_path / "image.pdf"
        fake_pdf.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        with pytest.raises(ValueError, match="not a valid PDF"):
            FileStorage._verify_pdf_content(fake_pdf)

    def test_empty_file_rejected(self, tmp_path):
        empty = tmp_path / "empty.pdf"
        empty.write_bytes(b"")
        with pytest.raises(ValueError, match="could not be determined"):
            FileStorage._verify_pdf_content(empty)


class TestValidateFilePathMime:
    @patch("src.api.storage.file_storage.get_settings")
    def test_html_with_pdf_extension_returns_400(self, mock_settings, tmp_path):
        mock_settings.return_value = MagicMock(
            storage_dir=tmp_path,
            max_file_size_bytes=50 * 1024 * 1024,
            max_file_size_mb=50,
        )
        fake_pdf = tmp_path / "fake.pdf"
        fake_pdf.write_text("<html><body>Not a PDF</body></html>")
        storage = FileStorage(base_dir=tmp_path)
        with pytest.raises(ValueError, match="not a valid PDF|could not be determined"):
            storage.validate_file_path(str(fake_pdf))

    @patch("src.api.storage.file_storage.get_settings")
    def test_real_pdf_passes_validation(self, mock_settings, tmp_path):
        mock_settings.return_value = MagicMock(
            storage_dir=tmp_path,
            max_file_size_bytes=50 * 1024 * 1024,
            max_file_size_mb=50,
        )
        real_pdf = tmp_path / "real.pdf"
        real_pdf.write_bytes(b"%PDF-1.4 fake but valid header content")
        storage = FileStorage(base_dir=tmp_path)
        result = storage.validate_file_path(str(real_pdf))
        assert result == real_pdf


class TestDownloadUrlToStorage:
    def _run_async(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("src.api.storage.file_storage.get_settings")
    def test_rejects_non_pdf_content_type(self, mock_settings, tmp_path):
        mock_settings.return_value = MagicMock(
            storage_dir=tmp_path,
            max_file_size_bytes=50 * 1024 * 1024,
            max_file_size_mb=50,
        )
        storage = FileStorage(base_dir=tmp_path)

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream)

        with patch("src.api.storage.file_storage.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="did not return a PDF.*text/html"):
                self._run_async(storage.download_url_to_storage(
                    "https://example.com/not-a-pdf", "test-file-id"
                ))

    @patch("src.api.storage.file_storage.get_settings")
    def test_rejects_downloaded_non_pdf_content(self, mock_settings, tmp_path):
        mock_settings.return_value = MagicMock(
            storage_dir=tmp_path,
            max_file_size_bytes=50 * 1024 * 1024,
            max_file_size_mb=50,
        )
        storage = FileStorage(base_dir=tmp_path)

        html_content = b"<html><body>Virus scan warning</body></html>"

        async def mock_aiter_bytes(chunk_size=8192):
            yield html_content

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"content-type": "application/octet-stream"}
        mock_response.aiter_bytes = mock_aiter_bytes

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream)

        with patch("src.api.storage.file_storage.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="not a valid PDF|could not be determined"):
                self._run_async(storage.download_url_to_storage(
                    "https://drive.google.com/uc?export=download&id=ABC", "test-file-id"
                ))

    @patch("src.api.storage.file_storage.get_settings")
    def test_accepts_valid_pdf_download(self, mock_settings, tmp_path):
        mock_settings.return_value = MagicMock(
            storage_dir=tmp_path,
            max_file_size_bytes=50 * 1024 * 1024,
            max_file_size_mb=50,
        )
        storage = FileStorage(base_dir=tmp_path)

        pdf_content = b"%PDF-1.4 fake but valid header content padding"

        async def mock_aiter_bytes(chunk_size=8192):
            yield pdf_content

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.aiter_bytes = mock_aiter_bytes

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream)

        with patch("src.api.storage.file_storage.httpx.AsyncClient", return_value=mock_client):
            result = self._run_async(storage.download_url_to_storage(
                "https://example.com/doc.pdf", "test-file-id"
            ))
            assert result.exists()
            assert result.name == "test-file-id.pdf"

    @patch("src.api.storage.file_storage.get_settings")
    def test_rejects_oversized_download(self, mock_settings, tmp_path):
        mock_settings.return_value = MagicMock(
            storage_dir=tmp_path,
            max_file_size_bytes=100,
            max_file_size_mb=0,
        )
        storage = FileStorage(base_dir=tmp_path)

        big_content = b"%PDF-" + b"x" * 200

        async def mock_aiter_bytes(chunk_size=8192):
            yield big_content

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.aiter_bytes = mock_aiter_bytes

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream)

        with patch("src.api.storage.file_storage.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="exceeds maximum"):
                self._run_async(storage.download_url_to_storage(
                    "https://example.com/big.pdf", "test-file-id"
                ))
