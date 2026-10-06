import argparse
from datetime import datetime
import logging
from pathlib import Path
import sys

from .download import OUTPUT_DIR, download
from .errors import DiskwalaError
from .resolver import resolve
from .urls import share_id


def _logs(verbose: bool) -> None:
    if not verbose:
        return
    folder = Path(__file__).resolve().parents[1] / "logs"
    folder.mkdir(exist_ok=True)
    filename = folder / f"resolver_{datetime.now():%Y%m%d_%H%M%S}.log"
    handler = logging.FileHandler(filename, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger("diskwala_downloader").addHandler(handler)
    logging.getLogger("diskwala_downloader").setLevel(logging.INFO)
    print(f"Diagnostic log: {filename}")


def inspect_url(url: str, verbose: bool = False) -> int:
    _logs(verbose)
    try:
        sid = share_id(url)
        print(f"Share ID: {sid}")
        info = resolve(url)
    except DiskwalaError as exc:
        print(f"Status: {exc.code}")
        print(f"Detail: {exc.message}")
        print("Direct URL available: no")
        return 2
    print("Status: RESOLVED")
    print(f"Filename: {info.filename or 'unknown'}")
    print(f"File size: {info.filesize if info.filesize is not None else 'unknown'}")
    print(f"Duration: {info.duration if info.duration is not None else 'unknown'}")
    print(f"Media type: {info.mime_type or 'unknown'}")
    print(f"Resolver method: {info.resolver_name}")
    print(f"Stream type: {info.stream_type or 'unknown'}")
    print(f"Direct URL available: {'yes' if info.stream_type else 'no'}")
    print(f"URL expiry: {info.expires_at.isoformat() if info.expires_at else 'unknown'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="diskwala", description="Download public DiskWala media to E:\\TeraBoxDownload\\Diskwala")
    p.add_argument("url", nargs="?", help="https://www.diskwala.com/app/<ID>")
    p.add_argument("--inspect", action="store_true", help="Resolve only; do not download")
    p.add_argument("--verbose", action="store_true", help="Write sanitized endpoint and status diagnostics")
    a = p.parse_args()
    if not a.url:
        p.print_help()
        return 1
    if a.inspect:
        return inspect_url(a.url, a.verbose)
    print("=" * 60)
    print("DiskWala Downloader")
    print("=" * 60)
    print(f"Resolving: {a.url}", flush=True)
    _logs(a.verbose)
    try:
        info = resolve(a.url)
        print(f"File: {info.filename or info.share_id}")
        print(f"Stream: {info.stream_type}")
        result = download(info)
        print(f"Saved: {result}")
        print("=" * 60)
        return 0
    except DiskwalaError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
