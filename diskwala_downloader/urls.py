import re
from urllib.parse import urlsplit

from .errors import DiskwalaError


_ID = re.compile(r"^[a-fA-F0-9]{24}$")


def share_id(url: str) -> str:
    try:
        p = urlsplit(url.strip())
    except ValueError as exc:
        raise DiskwalaError("INVALID_URL", "Malformed URL") from exc
    if p.scheme not in {"http", "https"} or (p.hostname or "").lower() not in {
        "diskwala.com", "www.diskwala.com"
    }:
        raise DiskwalaError("INVALID_URL", "Expected a diskwala.com share URL")
    parts = [x for x in p.path.split("/") if x]
    if len(parts) != 2 or parts[0].lower() != "app" or not _ID.fullmatch(parts[1]):
        raise DiskwalaError("INVALID_URL", "Expected /app/<24-character hexadecimal ID>")
    return parts[1].lower()
