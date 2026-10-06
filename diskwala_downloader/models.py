from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MediaInfo:
    original_url: str
    share_id: str
    filename: str | None = None
    filesize: int | None = None
    duration: float | None = None
    mime_type: str | None = None
    direct_url: str | None = None
    hls_url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    expires_at: datetime | None = None
    resolver_name: str = "official-public-web"

    @property
    def stream_type(self) -> str | None:
        if self.direct_url:
            return "direct"
        if self.hls_url:
            return "hls"
        return None
