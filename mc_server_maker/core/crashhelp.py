"""Why did the server stop? Plain-language causes for the common, certain failures in its log.

Only patterns that really identify the cause are matched; anything else is left to the log itself.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from mc_server_maker.i18n import t


@dataclass
class Diagnosis:
    kind: str  # port / java / memory / mod / eula / world
    title: str
    detail: str
    action: str = ""  # what the fix button does: port / java / memory / mod / eula / backups
    action_label: str = ""
    mod: str = ""  # missing mod id (kind "mod")


# the game's own port only: plugins (Geyser, RCON, web maps) log BindException for their ports too
_PORT = re.compile(r"FAILED TO BIND TO PORT|Perhaps a server is already running on that port")
_JAVA = re.compile(r"UnsupportedClassVersionError|compiled by a more recent version of the Java Runtime|"
                   r"requires running the server with Java|Unsupported Java detected|class file version (\d+)")
_MEMORY = re.compile(r"OutOfMemoryError|Could not reserve enough space for object heap|"
                     r"Invalid maximum heap size|Initial heap size set to a larger value")
_FABRIC_MOD = re.compile(r"requires (?:any version|version [^ ]+(?: or later)?) of (?:mod )?'?([^'(]+?)'? \(([\w.-]+)\)[^,]*, which is missing")
_FORGE_MOD = re.compile(r"Mod ID: '([\w.-]+)'.*?(?:Requested by|Currently)", re.S)
_FORGE_MISSING = re.compile(r"Missing or unsupported mandatory dependencies")
_EULA = re.compile(r"You need to agree to the EULA")
_WORLD = re.compile(r"Failed to load level|Exception reading .*level\.dat|Failed to read level|"
                    r"Couldn't load .*level\.dat|Corrupted chunk|Failed to load world")


def _last(pattern, text: str) -> int:
    """Where the pattern last matches (-1: not at all)."""
    pos = -1
    for m in pattern.finditer(text):
        pos = m.start()
    return pos


def diagnose(lines: List[str]) -> Optional[Diagnosis]:
    """The certain cause seen last in this run's log (the one that stopped it), or None."""
    text = "\n".join(lines[-400:])
    found = []
    if (pos := _last(_EULA, text)) >= 0:
        found.append((pos, Diagnosis("eula", t("The Minecraft EULA isn't accepted"),
                                     t("The server stops until the EULA (the game's license) is agreed to in eula.txt."),
                                     "eula", t("Agree to the EULA"))))
    if (pos := _last(_PORT, text)) >= 0:
        found.append((pos, Diagnosis("port", t("The server's port is already in use"),
                                     t("Another program (or another server) already uses this port, so the server can't open it."),
                                     "port", t("Use another port"))))
    if (pos := _last(_JAVA, text)) >= 0:
        found.append((pos, Diagnosis("java", t("The Java version doesn't fit this server"),
                                     t("This Minecraft version needs a different Java. Bartizan can install the right one."),
                                     "java", t("Install the right Java"))))
    if (pos := _last(_MEMORY, text)) >= 0:
        found.append((pos, Diagnosis("memory", t("Memory problem"),
                                     t("The server ran out of memory, or the PC couldn't give it the memory it was set to use."),
                                     "memory", t("Change memory"))))
    m = None
    for m in _FABRIC_MOD.finditer(text):
        pass
    if m:
        name, mod_id = m.group(1).strip(), m.group(2)
        found.append((m.start(), Diagnosis("mod", t("A required mod is missing"),
                                           t("A mod needs {name} ({id}), which isn't installed.", name=name, id=mod_id),
                                           "mod", t("Find {name}", name=name), mod=mod_id)))
    if (pos := _last(_FORGE_MISSING, text)) >= 0:
        fm = _FORGE_MOD.search(text, pos)
        mod_id = fm.group(1) if fm else ""
        found.append((pos, Diagnosis("mod", t("A required mod is missing"),
                                     t("A mod needs {name} ({id}), which isn't installed.", name=mod_id or "?", id=mod_id or "?"),
                                     "mod" if mod_id else "", t("Find {name}", name=mod_id) if mod_id else "", mod=mod_id)))
    if (pos := _last(_WORLD, text)) >= 0:
        found.append((pos, Diagnosis("world", t("The world couldn't be loaded"),
                                     t("The world files may be damaged. A backup from before can bring it back."),
                                     "backups", t("Open backups"))))
    return max(found, key=lambda f: f[0])[1] if found else None


_IPV4 = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.\d{1,3}\.\d{1,3}\b")


def shareable_log(lines: List[str], limit: int = 300) -> str:
    """The end of the log for asking someone for help: addresses and the user's folder hidden."""
    home = str(Path.home())
    out = []
    for line in lines[-limit:]:
        line = _IPV4.sub(lambda m: f"{m.group(1)}.{m.group(2)}.x.x", line)
        if home and len(home) > 3:
            line = line.replace(home, "~")
        user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        if len(user) > 2:
            line = line.replace(user, "<user>")
        out.append(line)
    return "\n".join(out)
