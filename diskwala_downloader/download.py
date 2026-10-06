import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

import requests

from .errors import DiskwalaError
from .models import MediaInfo


OUTPUT_DIR = Path(r"E:\TeraBoxDownload\Diskwala")
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_filename(name: str, fallback: str = "diskwala_video.mp4") -> str:
    name = _BAD.sub("_", name or "").strip(" .")
    if not name:
        name = fallback
    if name.split(".")[0].upper() in _RESERVED:
        name = "_" + name
    return name[:180].rstrip(" .") or fallback


def output_path(info: MediaInfo, folder: Path = OUTPUT_DIR) -> Path:
    name = info.filename or f"{info.share_id}.mp4"
    name = safe_filename(name)
    if not Path(name).suffix:
        name += ".mp4"
    return folder / name


def _target(info: MediaInfo, folder: Path) -> tuple[Path, bool]:
    base = output_path(info, folder)
    if base.exists() and info.filesize and base.stat().st_size == info.filesize:
        return base, True
    if not base.exists():
        return base, False
    for n in range(2, 1000):
        candidate = base.with_name(f"{base.stem} ({n}){base.suffix}")
        if not candidate.exists():
            return candidate, False
    raise DiskwalaError("DOWNLOAD_FAILED", "Too many files with the same name")


def download_direct(info: MediaInfo, folder: Path = OUTPUT_DIR, session: requests.Session | None = None) -> Path:
    if not info.direct_url or urlsplit(info.direct_url).scheme not in {"http", "https"}:
        raise DiskwalaError("RESOLVER_CHANGED", "No usable direct media URL")
    folder.mkdir(parents=True, exist_ok=True)
    target, exists = _target(info, folder)
    if exists:
        return target
    part = target.with_name(target.name + ".part")
    own_session = session is None
    s = session or requests.Session()
    try:
        for attempt in range(3):
            start = part.stat().st_size if part.exists() else 0
            headers = dict(info.headers)
            if start:
                headers["Range"] = f"bytes={start}-"
            try:
                with s.get(info.direct_url, headers=headers, stream=True, timeout=(10, 45)) as r:
                    if r.status_code in {401, 403}:
                        raise DiskwalaError("ACCESS_RESTRICTED", "Media URL rejected the download request")
                    if r.status_code == 404:
                        raise DiskwalaError("SHARE_EXPIRED", "Media URL expired or was removed")
                    if r.status_code >= 500 or r.status_code == 429:
                        raise requests.HTTPError(f"HTTP {r.status_code}")
                    if r.status_code not in {200, 206}:
                        raise DiskwalaError("DOWNLOAD_FAILED", f"Media server returned HTTP {r.status_code}")
                    content_type = r.headers.get("Content-Type", "").lower()
                    if "text/html" in content_type or "application/json" in content_type:
                        raise DiskwalaError("DOWNLOAD_FAILED", "Media URL returned a web page instead of a file")
                    mode = "ab" if start and r.status_code == 206 else "wb"
                    if mode == "ab":
                        content_range = r.headers.get("Content-Range", "")
                        if not content_range.startswith(f"bytes {start}-"):
                            raise DiskwalaError("DOWNLOAD_FAILED", "Invalid resume range from media server")
                    expected = info.filesize
                    begun = time.monotonic()
                    last_update = begun
                    with part.open(mode) as f:
                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                                if sys.stdout.isatty() and time.monotonic() - last_update >= 0.5:
                                    done = f.tell()
                                    speed = (done - (start if mode == "ab" else 0)) / max(time.monotonic() - begun, 0.001)
                                    percent = f"{done / expected * 100:5.1f}% " if expected else ""
                                    print(f"\rDownloading: {percent}{done / 1048576:.1f} MiB  {speed / 1048576:.1f} MiB/s", end="", flush=True)
                                    last_update = time.monotonic()
                    if sys.stdout.isatty():
                        print()
                    if expected and part.stat().st_size != expected:
                        raise requests.ConnectionError("Incomplete download")
                    os.replace(part, target)
                    return target
            except DiskwalaError:
                raise
            except (requests.RequestException, OSError) as exc:
                if attempt == 2:
                    raise DiskwalaError("DOWNLOAD_FAILED", "Media download failed after three attempts") from exc
                time.sleep(0.5 * (2 ** attempt))
    finally:
        if own_session:
            s.close()
    raise DiskwalaError("DOWNLOAD_FAILED", "Unexpected downloader state")


def download_hls(info: MediaInfo, folder: Path = OUTPUT_DIR) -> Path:
    if not info.hls_url:
        raise DiskwalaError("RESOLVER_CHANGED", "No HLS URL")
    try:
        import yt_dlp
    except ImportError as exc:
        raise DiskwalaError("DOWNLOAD_FAILED", "yt-dlp is required for HLS media") from exc
    folder.mkdir(parents=True, exist_ok=True)
    target, exists = _target(info, folder)
    if exists:
        return target
    options = {
        "outtmpl": str(target.with_suffix("")) + ".%(ext)s",
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "http_headers": info.headers,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "overwrites": False,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([info.hls_url])
    except Exception as exc:
        raise DiskwalaError("DOWNLOAD_FAILED", "HLS download failed; use --verbose for diagnostics") from exc
    candidates = [target, target.with_suffix(".mp4"), target.with_suffix(".mkv")]
    for candidate in candidates:
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    raise DiskwalaError("DOWNLOAD_FAILED", "yt-dlp reported success but no output file was found")


def download(info: MediaInfo, folder: Path = OUTPUT_DIR) -> Path:
    if info.direct_url:
        return download_direct(info, folder)
    if info.hls_url:
        return download_hls(info, folder)
    raise DiskwalaError("ACCESS_RESTRICTED", "The share has no public media URL")
