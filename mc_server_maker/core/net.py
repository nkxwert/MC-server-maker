"""HTTP 요청 / 파일 다운로드."""

import hashlib
import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from mc_server_maker import APP_VERSION
from mc_server_maker.core.tasks import Task

USER_AGENT = f"MC-Server-Maker/{APP_VERSION} (+https://github.com/nkxwert/MC-server-maker)"
TIMEOUT = 30


class NetError(Exception):
    pass


def _ssl_context() -> ssl.SSLContext:
    # macOS의 python.org 설치본은 인증서가 없을 수 있어서 certifi가 있으면 사용한다.
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_CTX = _ssl_context()


def _open(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        return urllib.request.urlopen(req, timeout=TIMEOUT, context=_CTX)
    except urllib.error.HTTPError as e:
        raise NetError(f"HTTP {e.code}: {url}") from e
    except urllib.error.URLError as e:
        raise NetError(f"연결 실패 ({e.reason}): {url}") from e


def get_json(url: str):
    with _open(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
) -> Path:
    """url을 dest에 내려받고 해시가 주어지면 검증한다."""
    task = task or Task()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    hashers = {
        name: (hashlib.new(name), expected.lower())
        for name, expected in (("sha1", sha1), ("sha256", sha256), ("md5", md5))
        if expected
    }
    task.log(f"다운로드: {url}")
    with _open(url) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            task.check()
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            for h, _ in hashers.values():
                h.update(chunk)
            done += len(chunk)
            task.progress(done, total)
    for name, (h, expected) in hashers.items():
        if h.hexdigest() != expected:
            tmp.unlink(missing_ok=True)
            raise NetError(f"파일 검증 실패({name}): {dest.name} - 다시 시도해 주세요.")
    tmp.replace(dest)
    return dest
