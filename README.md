# MC Server Maker

마인크래프트 서버를 **클릭 몇 번으로 만들고 관리**하는 GUI 프로그램입니다. (Windows / macOS / Linux)

## 실행 방법

1. [Python 3.10 이상](https://www.python.org/downloads/)을 설치합니다. (Windows는 설치할 때 **Add Python to PATH** 체크)
2. 이 폴더에서 실행:
   - **Windows**: `run.bat` 더블클릭
   - **macOS / Linux**: 터미널에서 `./run.sh`

처음 실행할 때 필요한 라이브러리(PySide6)를 `.venv` 폴더에 자동으로 설치합니다.

## 기능

### 1. 새 서버 만들기
- **구동기 선택**: Paper(추천) · Vanilla · Purpur · Fabric(모드) · Forge(모드)
- **버전 선택**: 각 구동기의 공식 서버에서 최신 버전 목록을 받아옵니다. (스냅샷/테스트 버전 표시 옵션)
- **메모리(RAM)** 설정
- **Java 자동 설치** (기본 켜짐): 버전에 맞는 Java(Eclipse Temurin 8/17/21/25)가 없으면 `runtime/` 폴더에 자동 설치
- **맵**: 무작위 생성 / 시드로 생성(🎲 무작위 시드 버튼) / 기존 맵 불러오기(폴더 또는 zip), 맵 종류(기본·평지·큰 생물 군계·확대)
- 서버 설명, 게임 모드, 난이도, 최대 인원, 포트, 정품 인증, PvP
- EULA 동의 후 자동 구축: 서버 파일 다운로드(해시 검증) → `eula.txt` → `server.properties` → `start.bat`/`start.sh` 생성

### 2. 서버 관리
| 탭 | 내용 |
|---|---|
| ⚙ 설정 | 서버 이름, **서버 설명(MOTD, `&a` 색 코드, 2줄)**, **서버 사진**(아무 이미지 → 64×64 자동 변환), 미리보기, 게임 설정, RAM |
| 🌍 맵 | 현재 시드 확인, **새 맵(무작위/시드)**, **맵 불러오기**, 맵 백업 (교체 전 자동 백업) |
| 👤 플레이어 | OP / 화이트리스트 추가·삭제 (서버가 켜져 있으면 명령어로 바로 적용) |
| 🖥 콘솔 | 서버 로그 보기, 명령어 입력 |
| ⬆ 업그레이드 | **서버 버전 업그레이드** (업그레이드 전 전체 백업, 필요한 Java 자동 설치), Java 다시 찾기 |

- 상단에 접속 주소(같은 PC: `localhost`, 같은 와이파이: 내부 IP)가 표시됩니다.
- 다른 곳(외부 인터넷)에서 접속하려면 공유기에서 포트(기본 25565) 포워딩이 필요합니다.

## 폴더 구조

```
servers/<서버 이름>/   만든 서버 (server-maker.json 에 구동기/버전 정보 저장)
  backups/             자동/수동 백업 zip
  start.bat, start.sh  프로그램 없이 서버를 켤 때
runtime/java-21/ ...   자동 설치된 Java
```

`MCSM_HOME` 환경 변수로 데이터 폴더 위치를 바꿀 수 있습니다.

## 개발

```
pip install -r requirements.txt
python -m mc_server_maker          # 실행
python -m unittest discover tests  # 테스트 (네트워크 불필요)
```

| 파일 | 역할 |
|---|---|
| `mc_server_maker/core/providers.py` | 구동기별 버전 목록 / 설치 (Mojang, PaperMC Fill v3, Purpur, Fabric meta, Forge maven) |
| `mc_server_maker/core/java.py` | Java 찾기 / Adoptium에서 자동 설치 |
| `mc_server_maker/core/server.py` | 서버 생성, 업그레이드, 맵, 백업, 실행 명령 |
| `mc_server_maker/core/properties.py` | `server.properties` 읽기/쓰기 (주석·순서 유지, 한글 안전) |
| `mc_server_maker/gui/` | PySide6 화면 |

> Spigot은 직접 컴파일(BuildTools)이 필요해서 지원하지 않습니다. Spigot 플러그인은 Paper에서 그대로 쓸 수 있어요.
