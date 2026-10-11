import httpx
import pytest
from artifact_download import download, DownloadRefused

ALLOWED = {"dograh.test", "files.test"}


def t(handler):
    return httpx.MockTransport(handler)


def test_http_scheme_refused():
    with pytest.raises(DownloadRefused, match="https"):
        download("http://dograh.test/x", ALLOWED, transport=t(lambda r: httpx.Response(200)))


def test_unlisted_host_refused_without_request():
    seen = []
    with pytest.raises(DownloadRefused, match="host"):
        download("https://evil.test/x", ALLOWED, transport=t(lambda r: seen.append(r) or httpx.Response(200)))
    assert seen == []


def test_redirect_to_allowed_storage_host_is_followed():
    def h(req):
        if req.url.host == "dograh.test":
            return httpx.Response(302, headers={"location": "https://files.test/obj"})
        return httpx.Response(200, content=b"data", headers={"content-type": "audio/wav"})
    assert download("https://dograh.test/d", ALLOWED, transport=t(h)) == ("audio/wav", b"data")


def test_redirect_to_other_host_refused():
    h = lambda req: httpx.Response(302, headers={"location": "https://evil.test/o"})
    with pytest.raises(DownloadRefused, match="host"):
        download("https://dograh.test/d", ALLOWED, transport=t(h))


def test_size_limit_enforced_on_stream():
    h = lambda req: httpx.Response(200, content=b"x" * 100)
    with pytest.raises(DownloadRefused, match="size"):
        download("https://dograh.test/d", ALLOWED, max_bytes=10, transport=t(h))


def test_redirect_loop_stops():
    h = lambda req: httpx.Response(302, headers={"location": "https://dograh.test/d"})
    with pytest.raises(DownloadRefused, match="redirect"):
        download("https://dograh.test/d", ALLOWED, transport=t(h))
