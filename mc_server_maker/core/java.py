"""Java 찾기 / 자동 설치 (Eclipse Temurin, Adoptium)."""

import os
import platform
import re
import shutil
import subprocess
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from mc_server_maker.core import net, paths
from mc_server_maker.core.tasks import Task

# Adoptium에서 받을 수 있는 LTS 버전
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
    bundled: bool  # 이 프로그램이 runtime/ 에 설치한 Java인지


def install_target(required: int) -> int:
    """필요 버전 이상인 가장 가까운 LTS (예: 16 -> 17)."""
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
    """알맞은 Java를 찾는다.

    strict=True 이면 권장 LTS 버전(예: 1.20.1 -> 17)과 정확히 같은 것만 고른다.
    너무 새로운 Java에서는 구버전 서버/모드가 깨지는 경우가 있기 때문이다.
    strict=False 이면 필요 버전 이상인 것 중 가장 낮은 것을 고른다.
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
        raise JavaError(f"지원하지 않는 OS입니다: {platform.system()}")
    machine = platform.machine().lower()
    arch = {
        "amd64": "x64",
        "x86_64": "x64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }.get(machine)
    if not arch:
        raise JavaError(f"지원하지 않는 CPU 종류입니다: {platform.machine()}")
    return os_name, arch


def _find_package(major: int, os_name: str, arch: str) -> dict:
    # JRE를 먼저 시도하고 없으면 JDK. Apple Silicon에 Java 8이 없으면 x64(Rosetta)로.
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
    raise JavaError(f"Java {major} 설치 파일을 찾지 못했습니다 ({os_name}/{arch}).")


def _safe_extract(archive: Path, dest: Path) -> None:
    dest_resolved = dest.resolve()
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if not (dest / name).resolve().is_relative_to(dest_resolved):
                    raise JavaError("압축 파일 경로가 올바르지 않습니다.")
            z.extractall(dest)
    else:
        with tarfile.open(archive) as t:
            try:
                t.extractall(dest, filter="data")
            except TypeError:  # 오래된 Python
                for m in t.getmembers():
                    if not (dest / m.name).resolve().is_relative_to(dest_resolved):
                        raise JavaError("압축 파일 경로가 올바르지 않습니다.")
                t.extractall(dest)


def install_java(required: int, task: Optional[Task] = None) -> JavaInfo:
    task = task or Task()
    major = install_target(required)
    os_name, arch = _platform()
    task.log(f"Java {major} 설치 파일을 찾는 중... ({os_name}/{arch})")
    pkg = _find_package(major, os_name, arch)
    paths.ensure_dirs()
    archive = paths.RUNTIME_DIR / pkg["name"]
    net.download(pkg["link"], archive, task, sha256=pkg.get("checksum"))
    target = _bundled_dir(major)
    tmp = target.with_name(target.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    task.log("압축 푸는 중...")
    _safe_extract(archive, tmp)
    archive.unlink(missing_ok=True)
    shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)
    exe = _find_exe(target)
    if not exe:
        raise JavaError("설치된 Java 실행 파일을 찾지 못했습니다.")
    if not IS_WINDOWS:
        exe.chmod(exe.stat().st_mode | 0o111)
    task.log(f"Java {major} 설치 완료: {exe}")
    return JavaInfo(str(exe), major, True)


def ensure_java(required: int, auto_install: bool, task: Optional[Task] = None) -> JavaInfo:
    """알맞은 Java를 찾고, 없으면 (자동 설치가 켜져 있을 때) 설치한다."""
    task = task or Task()
    target = install_target(required)
    java = find_java(required, strict=True)
    if java:
        task.log(f"Java {java.major} 사용: {java.path}")
        return java
    if auto_install:
        return install_java(required, task)
    java = find_java(required, strict=False)
    if java:
        task.log(f"주의: 권장 Java는 {target}인데 Java {java.major}을(를) 사용합니다: {java.path}")
        return java
    raise JavaError(
        f"Java {target} 이상이 필요하지만 설치된 Java를 찾지 못했습니다.\n"
        "'Java 자동 설치'를 켜거나 Java를 직접 설치해 주세요."
    )
