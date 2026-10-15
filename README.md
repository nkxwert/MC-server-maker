# MC Server Maker

마인크래프트 서버를 **클릭 몇 번으로 만들고 관리**하는 GUI 프로그램입니다. (Windows / macOS / Linux)

## 다운로드 (EXE)

GitHub의 **Actions → Build EXE → 가장 최근 실행 → Artifacts** 에서 `MC-Server-Maker-windows` 를 받으면
`MC-Server-Maker.exe` 가 들어 있습니다. `v1.1.0` 처럼 `v`로 시작하는 태그를 올리면 **Releases** 에도 자동으로 올라갑니다.

- EXE는 **빈 폴더에 넣고** 실행하세요. EXE 옆에 `servers/`, `runtime/` 폴더가 만들어집니다.
- 처음 실행할 때 Windows SmartScreen 경고가 뜨면 **추가 정보 → 실행** 을 누르세요. (코드 서명이 없는 프로그램이라 뜨는 경고입니다)

## 소스에서 실행

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
| 🖥 콘솔 | 색으로 구분된 서버 로그, 명령어 입력(↑↓ 이전 명령어), 빠른 명령 버튼(낮/밤/맑음/저장/접속자), **접속 중인 플레이어 목록**(OP 주기·추방), 가동 시간 |
| 🌐 외부 접속 | **다른 집에서 접속**: 공인 IP 주소 표시·복사, **UPnP로 공유기 포트 자동 열기**(서버 켤 때마다 자동 옵션), Windows 방화벽 허용, 직접 포트포워딩 안내 |
| ⬆ 업그레이드 | **서버 버전 업그레이드** (업그레이드 전 전체 백업, 필요한 Java 자동 설치), Java 다시 찾기 |

### 다른 집 친구와 같이 하기
1. **🌐 외부 접속** 탭 → **자동으로 포트 열기 (UPnP)** 를 누릅니다.
2. Windows라면 **Windows 방화벽 허용** 도 눌러 줍니다.
3. 친구에게 **다른 집 (인터넷)** 주소를 알려줍니다.

공유기 UPnP가 꺼져 있으면 탭의 안내대로 공유기 관리 페이지에서 포트포워딩(TCP 25565)을 직접 설정하세요.
통신사 NAT 뒤라 포트를 열 수 없는 경우(프로그램이 감지해서 알려줌)에는 [playit.gg](https://playit.gg) 같은 터널 서비스를 쓰면 됩니다.

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
pip install pyinstaller && python build_exe.py   # dist/ 에 실행 파일 생성
```

| 파일 | 역할 |
|---|---|
| `mc_server_maker/core/providers.py` | 구동기별 버전 목록 / 설치 (Mojang, PaperMC Fill v3, Purpur, Fabric meta, Forge maven) |
| `mc_server_maker/core/java.py` | Java 찾기 / Adoptium에서 자동 설치 |
| `mc_server_maker/core/server.py` | 서버 생성, 업그레이드, 맵, 백업, 실행 명령 |
| `mc_server_maker/core/network.py` | 공인 IP 확인, UPnP 포트 열기, 방화벽 |
| `mc_server_maker/core/properties.py` | `server.properties` 읽기/쓰기 (주석·순서 유지, 한글 안전) |
| `mc_server_maker/gui/` | PySide6 화면 |

> Spigot은 직접 컴파일(BuildTools)이 필요해서 지원하지 않습니다. Spigot 플러그인은 Paper에서 그대로 쓸 수 있어요.
