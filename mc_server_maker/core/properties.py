"""Read/write server.properties, keeping comments and order.

Follows Java .properties rules. Non-ASCII characters (Korean, '§', ...) are written as
\\uXXXX so every Minecraft version reads them correctly.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional


def unescape(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", s[i + 2 : i + 6]):
                out.append(chr(int(s[i + 2 : i + 6], 16)))
                i += 6
                continue
            out.append({"n": "\n", "t": "\t", "r": "\r", "f": "\f"}.get(n, n))
            i += 2
            continue
        out.append(c)
        i += 1
    # join split UTF-16 surrogate pairs (e.g. emoji)
    return "".join(out).encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


def escape(s: str, is_key: bool = False) -> str:
    out = []
    for i, c in enumerate(s):
        if c == "\\":
            out.append("\\\\")
        elif c == "\n":
            out.append("\\n")
        elif c == "\t":
            out.append("\\t")
        elif c == "\r":
            out.append("\\r")
        elif c == "\f":
            out.append("\\f")
        elif c in "=:#!":
            out.append("\\" + c)
        elif c == " " and (is_key or i == 0):
            out.append("\\ ")
        elif ord(c) > 126 or ord(c) < 32:
            out.append("".join(f"\\u{b:04x}" for b in _utf16(c)))
        else:
            out.append(c)
    return "".join(out)


def _utf16(c: str) -> List[int]:
    data = c.encode("utf-16-be")
    return [int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2)]


def _split_line(line: str):
    """Split a 'key=value' line (escaped separators are ignored)."""
    i = 0
    while i < len(line):
        c = line[i]
        if c == "\\":
            i += 2
            continue
        if c in "=:" or c.isspace():
            key = line[:i]
            rest = line[i:].lstrip()
            if rest[:1] in ("=", ":"):
                rest = rest[1:].lstrip()
            return unescape(key), unescape(rest)
        i += 1
    return unescape(line), ""


class Properties:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lines: List[str] = []
        self.values: Dict[str, str] = {}
        self._index: Dict[str, int] = {}
        if self.path.exists():
            self._load()
        else:
            self.lines.append("#Minecraft server properties (Bartizan)")

    def _load(self):
        raw = self.path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        # join lines continued with a trailing backslash
        logical: List[str] = []
        buf = ""
        for line in text.splitlines():
            stripped = line.lstrip() if buf else line
            if re.search(r"(?<!\\)(\\\\)*\\$", stripped):
                buf += stripped[:-1]
                continue
            logical.append(buf + stripped)
            buf = ""
        if buf:
            logical.append(buf)
        for line in logical:
            s = line.strip()
            if s and not s.startswith(("#", "!")):
                key, value = _split_line(s)
                self.values[key] = value
                self._index[key] = len(self.lines)
            self.lines.append(line)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.values.get(key, default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        v = self.values.get(key)
        return default if v is None else v.strip().lower() == "true"

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.values.get(key, default))
        except (TypeError, ValueError):
            return default

    def set(self, key: str, value) -> None:
        if isinstance(value, bool):
            value = "true" if value else "false"
        value = str(value)
        self.values[key] = value
        line = f"{escape(key, True)}={escape(value)}"
        if key in self._index:
            self.lines[self._index[key]] = line
        else:
            self._index[key] = len(self.lines)
            self.lines.append(line)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
