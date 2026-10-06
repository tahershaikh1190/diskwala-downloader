import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from diskwala_downloader.download import download, download_direct, output_path, safe_filename
from diskwala_downloader.errors import DiskwalaError
from diskwala_downloader.models import MediaInfo
from diskwala_downloader.resolver import classify_http, detect_expiry, parse_metadata, parse_public_html, resolve
from diskwala_downloader.urls import share_id

URL = "https://www.diskwala.com/app/6ac4fca22a52418b24b26ce2"
SID = "6ac4fca22a52418b24b26ce2"


class FakeResponse:
    def __init__(self, status=200, text="", data=None, body=b"", headers=None):
        self.status_code, self.text, self._data = status, text, data
        self.body, self.headers = body, headers or {}

    def json(self):
        return self._data

    def iter_content(self, chunk_size=1):
        yield self.body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class CoreTests(unittest.TestCase):
    def test_url_recognition(self):
        self.assertEqual(share_id(URL), SID)
        self.assertEqual(share_id(URL + "?x=1"), SID)
        for bad in ("https://evil.com/app/" + SID, "file:///app/" + SID,
                    "https://diskwala.com/app/nope"):
            with self.assertRaises(DiskwalaError):
                share_id(bad)

    def test_public_html_direct_and_hls(self):
        mp4 = parse_public_html(URL, '<video src="https://cdn.example/test.mp4"></video>', SID)
        self.assertEqual(mp4.stream_type, "direct")
        hls = parse_public_html(URL, '<source src="https://cdn.example/test.m3u8">', SID)
        self.assertEqual(hls.stream_type, "hls")

    def test_metadata_parsing(self):
        info = MediaInfo(URL, SID)
        got = parse_metadata({"fileInfo": {"name": "film.mp4", "type": "video/mp4",
                                            "size": "123", "url": "https://cdn.example/f.mp4"}}, info)
        self.assertEqual((got.filename, got.filesize, got.stream_type), ("film.mp4", 123, "direct"))
        with self.assertRaises(DiskwalaError) as cm:
            parse_metadata({"fileInfo": {"name": "film.mp4"}}, MediaInfo(URL, SID))
        self.assertEqual(cm.exception.code, "ACCESS_RESTRICTED")

    def test_error_classification(self):
        for status, code in ((403, "ACCESS_RESTRICTED"), (404, "SHARE_EXPIRED"),
                             (410, "FILE_DELETED"), (500, "DISKWALA_SERVER_ERROR")):
            self.assertEqual(classify_http(status).code, code)
        self.assertEqual(classify_http(400, "Missing Appicrypt header").code, "ACCESS_RESTRICTED")

    def test_official_page_probe(self):
        session = Mock()
        session.get.return_value = FakeResponse(text="<html><title>DiskWala</title></html>")
        session.post.return_value = FakeResponse(status=400, text="Missing Appicrypt header")
        with self.assertRaises(DiskwalaError) as cm:
            resolve(URL, session=session)
        self.assertEqual(cm.exception.code, "ACCESS_RESTRICTED")
        self.assertEqual(session.post.call_args.kwargs["json"], {"id": SID})

    def test_filename_and_output(self):
        self.assertEqual(safe_filename('CON?.mp4'), 'CON_.mp4')
        self.assertEqual(safe_filename('..'), 'diskwala_video.mp4')
        got = output_path(MediaInfo(URL, SID, filename='a<b>.mp4'), Path('X:/out'))
        self.assertEqual(got.name, 'a_b_.mp4')

    def test_download_selection(self):
        info = MediaInfo(URL, SID, direct_url="https://cdn.example/a.mp4", hls_url="https://cdn.example/a.m3u8")
        with patch('diskwala_downloader.download.download_direct', return_value=Path('a.mp4')) as direct:
            self.assertEqual(download(info, Path('x')), Path('a.mp4'))
            direct.assert_called_once()
        hls_only = MediaInfo(URL, SID, hls_url="https://cdn.example/a.m3u8")
        with patch('diskwala_downloader.download.download_hls', return_value=Path('a.mp4')) as hls:
            self.assertEqual(download(hls_only, Path('x')), Path('a.mp4'))
            hls.assert_called_once()

    def test_expiration_detection(self):
        self.assertEqual(detect_expiry('https://cdn.example/a.mp4?exp=1760000000').timestamp(), 1760000000)
        self.assertIsNone(detect_expiry('https://cdn.example/a.mp4'))

    def test_resume_and_atomic_finish(self):
        with tempfile.TemporaryDirectory() as td:
            info = MediaInfo(URL, SID, filename="x.mp4", filesize=6, direct_url="https://cdn.example/x.mp4")
            part = Path(td) / "x.mp4.part"
            part.write_bytes(b"abc")
            session = Mock()
            session.get.return_value = FakeResponse(status=206, body=b"def", headers={"Content-Range": "bytes 3-5/6"})
            result = download_direct(info, Path(td), session)
            self.assertEqual(result.read_bytes(), b"abcdef")
            self.assertFalse(part.exists())
            self.assertEqual(session.get.call_args.kwargs["headers"]["Range"], "bytes=3-")

    def test_retry_then_success(self):
        with tempfile.TemporaryDirectory() as td:
            info = MediaInfo(URL, SID, filename="x.mp4", filesize=3, direct_url="https://cdn.example/x.mp4")
            session = Mock()
            session.get.side_effect = [requests.ConnectionError("transient"), FakeResponse(body=b"abc")]
            with patch('diskwala_downloader.download.time.sleep'):
                result = download_direct(info, Path(td), session)
            self.assertEqual(result.read_bytes(), b"abc")
            self.assertEqual(session.get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
