"""HTTP requests / file downloads."""

import hashlib
import http.client
import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from mc_server_maker import APP_VERSION
from mc_server_maker.i18n import t
from mc_server_maker.core.tasks import Task

USER_AGENT = f"Bartizan/{APP_VERSION} (+https://github.com/nkxwert/MC-server-maker)"
TIMEOUT = 30


class NetError(Exception):
    pass


def _ssl_context() -> ssl.SSLContext:
    # python.org builds on macOS may lack CA certificates; prefer certifi when available.
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_CTX = _ssl_context()


def _open(url: str, body: Optional[bytes] = None, content_type: str = "", extra_headers: Optional[dict] = None):
    headers = {"User-Agent": USER_AGENT}
    if content_type:
        headers["Content-Type"] = content_type
    headers.update(extra_headers or {})
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        return urllib.request.urlopen(req, timeout=TIMEOUT, context=_CTX)
    except urllib.error.HTTPError as e:
        raise NetError(f"HTTP {e.code}: {url}") from e
    except urllib.error.URLError as e:
        raise NetError(t("Connection failed ({reason}): {url}", reason=e.reason, url=url)) from e
    except (OSError, http.client.HTTPException) as e:  # timeouts, dropped connections
        raise NetError(t("Connection failed ({reason}): {url}", reason=e, url=url)) from e


def _read(url: str, body: Optional[bytes] = None, content_type: str = "", limit: int = -1,
          extra_headers: Optional[dict] = None) -> bytes:
    with _open(url, body, content_type, extra_headers) as resp:
        try:
            return resp.read(limit)
        except (OSError, http.client.HTTPException) as e:
            raise NetError(t("Connection failed ({reason}): {url}", reason=e, url=url)) from e


def _json(data: bytes, url: str):
    try:
        return json.loads(data.decode("utf-8"))
    except ValueError as e:  # e.g. an HTML error page instead of JSON
        raise NetError(t("Unexpected answer from {url}", url=url)) from e


def get_json(url: str):
    return _json(_read(url), url)


def post_json(url: str, payload, headers: Optional[dict] = None):
    """POST a JSON body and return the JSON answer."""
    return _json(_read(url, json.dumps(payload).encode("utf-8"), "application/json", extra_headers=headers), url)


def get_bytes(url: str, limit: int = 2 * 1024 * 1024) -> bytes:
    """Small downloads kept in memory (icons). Stops at `limit` bytes."""
    return _read(url, limit=limit)


def get_text(url: str) -> str:
    return _read(url).decode("utf-8", errors="replace")


def exists(url: str) -> bool:
    try:
        with _open(url):
            return True
    except NetError:
        return False


def download(
    url: str,
    dest: Path,
    task: Optional[Task] = None,
    sha1: Optional[str] = None,
    sha256: Optional[str] = None,
    md5: Optional[str] = None,
    sha512: Optional[str] = None,
) -> Path:
    """Download url to dest, verifying the hash when one is given."""
    task = task or Task()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    hashers = {
        name: (hashlib.new(name), expected.lower())
        for name, expected in (("sha1", sha1), ("sha256", sha256), ("md5", md5), ("sha512", sha512))
        if expected
    }
    task.log(t("Downloading: {url}", url=url))
    try:
        with _open(url) as resp, open(tmp, "wb") as f:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                task.check()
                try:
                    chunk = resp.read(256 * 1024)
                except (OSError, http.client.HTTPException) as e:
                    raise NetError(t("Connection failed ({reason}): {url}", reason=e, url=url)) from e
                if not chunk:
                    break
                f.write(chunk)
                for h, _ in hashers.values():
                    h.update(chunk)
                done += len(chunk)
                task.progress(done, total)
    except BaseException:  # cancelled, disk full, connection lost: no half file left behind
        tmp.unlink(missing_ok=True)
        raise
    if total and done != total:  # the connection closed early: never keep a cut-off file
        tmp.unlink(missing_ok=True)
        raise NetError(t("The download was cut off. Please try again: {file}", file=dest.name))
    for name, (h, expected) in hashers.items():
        if h.hexdigest() != expected:
            tmp.unlink(missing_ok=True)
            raise NetError(t("File check failed ({algo}): {file} - please try again.", algo=name, file=dest.name))
    try:
        tmp.replace(dest)
    except OSError:  # the destination is locked (antivirus, Explorer): don't leave the .part
        tmp.unlink(missing_ok=True)
        raise
    return dest
