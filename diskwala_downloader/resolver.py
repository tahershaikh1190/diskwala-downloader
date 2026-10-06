"""Resolve media exposed by the official public web page.

The current site provides metadata only and directs viewers to its app. This
module deliberately does not forge app integrity headers or reuse private APIs.
"""
import html
from html.parser import HTMLParser
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .errors import DiskwalaError
from .models import MediaInfo
from .urls import share_id

LOG = logging.getLogger(__name__)
UA = "DiskwalaDownloader/0.1 (public web share resolver)"
META_ENDPOINT = "https://ddudapidd.diskwala.com/api/v1/file/temp_info"


def _public_http(url: str) -> bool:
    p = urlsplit(url)
    return p.scheme in {"http", "https"} and bool(p.hostname)


def _media_kind(url: str) -> str | None:
    path = urlsplit(url).path.lower()
    if path.endswith(".m3u8"):
        return "hls"
    if path.endswith((".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v")):
        return "direct"
    return None


def detect_expiry(url: str) -> datetime | None:
    query = {k.lower(): v[0] for k, v in parse_qs(urlsplit(url).query).items() if v}
    for key in ("expires", "exp", "expiry"):
        value = query.get(key)
        if value and value.isdigit():
            try:
                return datetime.fromtimestamp(int(value), timezone.utc)
            except (ValueError, OverflowError, OSError):
                pass
    issued, ttl = query.get("x-amz-date"), query.get("x-amz-expires")
    if issued and ttl and ttl.isdigit():
        try:
            return datetime.strptime(issued, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc) + timedelta(seconds=int(ttl))
        except (ValueError, OverflowError):
            pass
    return None


class _MediaParser(HTMLParser):
    def __init__(self, base: str):
        super().__init__()
        self.base = base
        self.urls: list[str] = []
        self.title: str | None = None
        self._in_title = False
        self._json_ld = False
        self._script_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in {"video", "source"} and a.get("src"):
            self.urls.append(urljoin(self.base, html.unescape(a["src"])))
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key in {"og:video", "og:video:url", "twitter:player:stream"} and a.get("content"):
                self.urls.append(urljoin(self.base, html.unescape(a["content"])))
            if key in {"og:title", "twitter:title"} and a.get("content"):
                self.title = html.unescape(a["content"])
        self._in_title = tag == "title"
        self._json_ld = tag == "script" and a.get("type") == "application/ld+json"
        if self._json_ld:
            self._script_text = []

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()
        if self._json_ld:
            self._script_text.append(data)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._json_ld:
            self._json_ld = False
            try:
                value = json.loads("".join(self._script_text))
            except ValueError:
                return
            for obj in value if isinstance(value, list) else [value]:
                if isinstance(obj, dict):
                    for key in ("contentUrl", "embedUrl"):
                        if isinstance(obj.get(key), str):
                            self.urls.append(urljoin(self.base, obj[key]))


def parse_public_html(url: str, page: str, sid: str) -> MediaInfo:
    parser = _MediaParser(url)
    parser.feed(page)
    info = MediaInfo(original_url=url, share_id=sid)
    if parser.title and "DiskWala" not in parser.title:
        info.filename = parser.title
    for candidate in parser.urls:
        if not _public_http(candidate):
            continue
        kind = _media_kind(candidate)
        if kind == "direct" and not info.direct_url:
            info.direct_url = candidate
            info.expires_at = detect_expiry(candidate)
        elif kind == "hls" and not info.hls_url:
            info.hls_url = candidate
            info.expires_at = detect_expiry(candidate)
    return info


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": UA})
    return s


def classify_http(status: int, text: str = "") -> DiskwalaError:
    if status in {401, 403}:
        return DiskwalaError("ACCESS_RESTRICTED", "The share requires authorization")
    if status == 404:
        return DiskwalaError("SHARE_EXPIRED", "The share was not found; it may have expired or been removed")
    if status == 410:
        return DiskwalaError("FILE_DELETED", "The file has been removed")
    if status >= 500:
        return DiskwalaError("DISKWALA_SERVER_ERROR", f"DiskWala returned HTTP {status}")
    if "missing appicrypt" in text.lower():
        return DiskwalaError("ACCESS_RESTRICTED", "The public API requires an app-generated integrity header")
    return DiskwalaError("RESOLVER_CHANGED", f"Unexpected DiskWala HTTP {status}")


def resolve(url: str, session: requests.Session | None = None) -> MediaInfo:
    sid = share_id(url)
    own_session = session is None
    s = session or _session()
    try:
        try:
            LOG.info("GET %s", urlsplit(url).path)
            response = s.get(url, timeout=(10, 30))
        except requests.RequestException as exc:
            raise DiskwalaError("NETWORK_ERROR", "Could not reach the DiskWala share page") from exc
        if response.status_code != 200:
            raise classify_http(response.status_code)
        info = parse_public_html(url, response.text, sid)
        if info.stream_type:
            info.headers["Referer"] = url
            LOG.info("Selected public HTML media: %s", info.stream_type)
            return info
        # This read-only probe explains why the current React share page is
        # insufficient. No app cryptogram, cookie, or account token is forged.
        try:
            LOG.info("POST /api/v1/file/temp_info (public probe)")
            probe = s.post(META_ENDPOINT, json={"id": sid}, timeout=(10, 15))
        except requests.RequestException as exc:
            raise DiskwalaError("NETWORK_ERROR", "Could not reach the DiskWala metadata API") from exc
        LOG.info("Metadata probe HTTP %s", probe.status_code)
        if probe.status_code != 200:
            raise classify_http(probe.status_code, probe.text[:200])
        try:
            data = probe.json()
        except ValueError as exc:
            raise DiskwalaError("RESOLVER_CHANGED", "Metadata API returned non-JSON data") from exc
        return parse_metadata(data, info)
    finally:
        if own_session:
            s.close()


def parse_metadata(data: dict, info: MediaInfo) -> MediaInfo:
    if not isinstance(data, dict):
        raise DiskwalaError("RESOLVER_CHANGED", "Metadata response is not an object")
    item = data.get("fileInfo")
    if not item and isinstance(data.get("data"), dict):
        item = data["data"].get("fileInfo")
    if not isinstance(item, dict):
        raise DiskwalaError("RESOLVER_CHANGED", "Metadata response lacks fileInfo")
    info.filename = item.get("name") or info.filename
    info.mime_type = item.get("type")
    try:
        info.filesize = int(item["size"]) if item.get("size") is not None else None
    except (ValueError, TypeError):
        pass
    candidate = item.get("url")
    if isinstance(candidate, str) and _public_http(candidate):
        if _media_kind(candidate) == "hls":
            info.hls_url = candidate
        else:
            info.direct_url = candidate
        info.expires_at = detect_expiry(candidate)
    if not info.stream_type:
        raise DiskwalaError("ACCESS_RESTRICTED", "The web response has metadata but no public media URL; DiskWala directs viewers to its app")
    return info
