"""SSRF-guarded artifact download: https only, host allowlist on every hop, size and time limits."""
from urllib.parse import urljoin, urlsplit

import httpx


class DownloadRefused(Exception):
    pass


def _check(url: str, allowed_hosts: set) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise DownloadRefused("https only")
    if parts.hostname not in allowed_hosts:
        raise DownloadRefused(f"host not allowed: {parts.hostname}")


def download(url, allowed_hosts, max_bytes=50_000_000, timeout_s=30.0, max_hops=2, transport=None):
    """Return (content_type, bytes). Each redirect hop is re-validated against the allowlist."""
    allowed = set(allowed_hosts)
    with httpx.Client(follow_redirects=False, timeout=timeout_s, transport=transport) as http:
        for _ in range(max_hops + 1):
            _check(url, allowed)
            with http.stream("GET", url) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, r.headers.get("location", ""))
                    continue
                if r.status_code != 200:
                    raise DownloadRefused(f"status {r.status_code}")
                if int(r.headers.get("content-length", 0)) > max_bytes:
                    raise DownloadRefused("declared size too large")
                data = bytearray()
                for chunk in r.iter_bytes():
                    data += chunk
                    if len(data) > max_bytes:
                        raise DownloadRefused("size limit exceeded")
                return r.headers.get("content-type", ""), bytes(data)
    raise DownloadRefused("too many redirects")
