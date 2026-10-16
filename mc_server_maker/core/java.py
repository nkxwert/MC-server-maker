"""Find Java / install it automatically (Eclipse Temurin via Adoptium)."""

import os
import platform
import re
import shutil
import subprocess
import tarfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from mc_server_maker.core import net, paths
from mc_server_maker.core.tasks import Task
from mc_server_maker.i18n import t

# LTS versions available from Adoptium
LTS_VERSIONS = (8, 11, 17, 21, 25)
IS_WINDOWS = os.name == "nt"
JAVA_EXE = "java.exe" if IS_WINDOWS else "java"
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW


class JavaError(Exception):
    pass


@dataclass
class JavaInfo:
    path: str
    major: int
    bundled: bool  # installed by this app into runtime/


def install_target(required: int) -> int:
    """Closest LTS at or above the required version (e.g. 16 -> 17)."""
    for v in LTS_VERSIONS:
        if v >= required:
            return v
    return required


def java_major(java_path: str) -> Optional[int]:
    try:
        out = subprocess.run(
            [java_path, "-version"],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r'version "([^"]+)"', out.stderr + out.stdout)
    if not m:
        return None
    parts = m.group(1).split(".")
    try:
        first = int(re.match(r"\d+", parts[0]).group())
        if first == 1 and len(parts) > 1:  # "1.8.0_392" -> 8
            return int(re.match(r"\d+", parts[1]).group())
        return first
    except (AttributeError, ValueError):
        return None


def _bundled_dir(major: int) -> Path:
    return paths.RUNTIME_DIR / f"java-{major}"


def _find_exe(root: Path) -> Optional[Path]:
    for p in sorted(root.rglob(JAVA_EXE)):
        if p.parent.name == "bin" and p.is_file():
            return p
    return None


def find_java_candidates() -> List[JavaInfo]:
    found: List[JavaInfo] = []
    seen = set()
    if paths.RUNTIME_DIR.exists():
        for d in sorted(paths.RUNTIME_DIR.glob("java-*")):
            if d.name.endswith((".tmp", ".old")):  # an install in progress or being replaced
                continue
            exe = _find_exe(d)
            if exe:
                major = java_major(str(exe))
                if major:
                    found.append(JavaInfo(str(exe), major, True))
                    seen.add(str(exe))
    system = []
    if os.environ.get("JAVA_HOME"):
        system.append(str(Path(os.environ["JAVA_HOME"]) / "bin" / JAVA_EXE))
    which = shutil.which("java")
    if which:
        system.append(which)
    for exe in system:
        if exe in seen or not Path(exe).exists():
            continue
        seen.add(exe)
        major = java_major(exe)
        if major:
            found.append(JavaInfo(exe, major, False))
    return found


def find_java(required: int, strict: bool = True) -> Optional[JavaInfo]:
    """Pick a suitable Java.

    strict=True only accepts the recommended LTS (e.g. 1.20.1 -> 17), because old
    servers and mods can break on much newer Java. strict=False accepts the lowest
    version that is at least `required`.
    """
    target = install_target(required)
    candidates = find_java_candidates()
    exact = [j for j in candidates if j.major == target]
    if exact:
        return sorted(exact, key=lambda j: not j.bundled)[0]
    if strict:
        return None
    ok = [j for j in candidates if j.major >= required]
    return min(ok, key=lambda j: j.major) if ok else None


def _platform() -> tuple:
    system = platform.system().lower()
    os_name = {"windows": "windows", "darwin": "mac", "linux": "linux"}.get(system)
    if not os_name:
        raise JavaError(t("Unsupported OS: {os}", os=platform.system()))
    machine = platform.machine().lower()
    arch = {
        "amd64": "x64",
        "x86_64": "x64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }.get(machine)
    if not arch:
        raise JavaError(t("Unsupported CPU: {cpu}", cpu=platform.machine()))
    return os_name, arch


def _find_package(major: int, os_name: str, arch: str) -> dict:
    # Try a JRE first, then a JDK. Apple Silicon without Java 8 falls back to x64 (Rosetta).
    archs = [arch] + (["x64"] if os_name == "mac" and arch == "aarch64" else [])
    for a in archs:
        for image in ("jre", "jdk"):
            url = (
                f"https://api.adoptium.net/v3/assets/latest/{major}/hotspot"
                f"?architecture={a}&image_type={image}&os={os_name}&vendor=eclipse"
            )
            try:
                assets = net.get_json(url)
            except net.NetError:
                continue
            if assets:
                return assets[0]["binary"]["package"]
    raise JavaError(t("Could not find a Java {v} download ({os}/{arch}).", v=major, os=os_name, arch=arch))


def _safe_extract(archive: Path, dest: Path) -> None:
    dest_resolved = dest.resolve()
    bad = t("The archive contains an invalid path.")
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if not (dest / name).resolve().is_relative_to(dest_resolved):
                    raise JavaError(bad)
            z.extractall(dest)
    else:
        with tarfile.open(archive) as tf:
            try:
                tf.extractall(dest, filter="data")
            except TypeError:  # older Python
                for m in tf.getmembers():
                    if not (dest / m.name).resolve().is_relative_to(dest_resolved):
                        raise JavaError(bad)
                tf.extractall(dest)


def install_java(required: int, task: Optional[Task] = None) -> JavaInfo:
    task = task or Task()
    major = install_target(required)
    os_name, arch = _platform()
    task.log(t("Looking for Java {v} ({os}/{arch})...", v=major, os=os_name, arch=arch))
    pkg = _find_package(major, os_name, arch)
    paths.ensure_dirs()
    archive = paths.RUNTIME_DIR / pkg["name"]
    net.download(pkg["link"], archive, task, sha256=pkg.get("checksum"))
    target = _bundled_dir(major)
    tmp = target.with_name(target.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    task.log(t("Extracting..."))
    try:
        _safe_extract(archive, tmp)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    finally:
        archive.unlink(missing_ok=True)
    old = None
    if target.exists():
        # move the old one aside first: if a running server holds it (Windows), keep it intact
        old = target.with_name(target.name + ".old")
        shutil.rmtree(old, ignore_errors=True)
        try:
            target.rename(old)
        except OSError as e:
            shutil.rmtree(tmp, ignore_errors=True)
            raise JavaError(t("Java {v} is in use. Stop the servers using it, then try again. ({err})", v=major, err=e)) from e
    for attempt in range(5):  # antivirus may hold the freshly unpacked java.exe for a moment
        try:
            tmp.rename(target)
            break
        except OSError:
            if attempt == 4:
                if old is not None:
                    old.rename(target)  # put the previous Java back
                shutil.rmtree(tmp, ignore_errors=True)
                raise
            time.sleep(1)
    if old is not None:
        shutil.rmtree(old, ignore_errors=True)
    exe = _find_exe(target)
    if not exe:
        raise JavaError(t("Installed Java executable not found."))
    if not IS_WINDOWS:
        exe.chmod(exe.stat().st_mode | 0o111)
    task.log(t("Java {v} installed: {path}", v=major, path=exe))
    return JavaInfo(str(exe), major, True)


def ensure_java(required: int, auto_install: bool, task: Optional[Task] = None) -> JavaInfo:
    """Find a suitable Java, installing one if allowed and needed."""
    task = task or Task()
    target = install_target(required)
    java = find_java(required, strict=True)
    if java:
        task.log(t("Using Java {v}: {path}", v=java.major, path=java.path))
        return java
    if auto_install:
        return install_java(required, task)
    java = find_java(required, strict=False)
    if java:
        task.log(t("Note: Java {want} is recommended, using Java {have}: {path}", want=target, have=java.major, path=java.path))
        return java
    raise JavaError(t("Java {v} or newer is required but none was found.\nTurn on 'Install Java automatically' or install Java yourself.", v=target))
