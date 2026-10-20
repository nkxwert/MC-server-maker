# Changelog

Each version has an English and a Korean list. The release workflow publishes the section for the
current version as the GitHub Release notes, and the app shows it as "What's new".

## 1.26.1
### en
- The player window opens at its full size (no small window growing; Windows' own zoom animation is off under our fade-in).
- Backups: no automatic backup after a crash, a failed start or a force stop, or when the world hasn't changed, so good backups aren't pushed out. The backup just made is never pruned, even if the PC clock was set back. Restoring moves the old world aside first and puts it back if anything fails (a file locked by antivirus or OneDrive). Delete / duplicate wait while a backup is being written. Leftovers of a backup cut off by a shutdown are cleaned up.
- Players: on online servers, ban / OP / whitelist use the player's real account ID even if an offline run left another one.
- Save and restart: waits for the automatic backup, can be cancelled with Stop, and never starts a server again while the app is closing.
- Crash helper: looks at the last run only and picks the cause that stopped it (a plugin's busy port, e.g. Geyser, no longer reads as "port in use").
- Start check: a server's own port right after a stop isn't reported as taken.
- Windows startup: starts the chosen server without waiting on a question for mere warnings (they go to the console).
### ko
- 플레이어 창이 처음부터 제 크기로 열려요 (작은 창이 커지던 현상: 우리 페이드인 아래에서 Windows 자체 확대 애니메이션을 껐어요).
- 백업: 크래시·시작 실패·강제 종료 뒤나 월드가 바뀌지 않았을 때는 자동 백업을 만들지 않아서 좋은 백업이 밀려 지워지지 않아요. 방금 만든 백업은 PC 시계가 뒤로 가도 지우지 않아요. 복원할 때 기존 월드를 먼저 옆으로 옮겨 두고, 실패하면(백신·OneDrive가 파일을 잠근 경우 등) 원래대로 되돌려요. 백업 중에는 서버 삭제·복제를 기다려요. 컴퓨터가 꺼져 중간에 끊긴 백업 조각은 정리해요.
- 플레이어: 정품 인증 서버에서 밴·OP·화이트리스트가 오프라인 실행 때 남은 ID가 아니라 진짜 계정 ID를 써요.
- 저장하고 재시작: 자동 백업이 끝나면 켜요. 중지를 누르면 취소되고, 앱을 끄는 중에는 다시 켜지 않아요.
- 오류 도우미: 이번 실행의 로그만 보고, 실제로 서버를 멈춘 원인을 골라요 (Geyser 같은 플러그인 포트 문제를 "포트 사용 중"으로 착각하지 않아요).
- 시작 전 점검: 방금 끈 서버의 포트를 "사용 중"으로 잘못 알리지 않아요.
- Windows 시작 시 실행: 단순 경고 때문에 질문 창에서 멈추지 않고 고른 서버를 켜요 (경고는 콘솔에 남겨요).

## 1.26.0
### en
- **Backup manager** (Settings → World → Manage backups): see every backup with its date, kind and size and **restore** one. The current world is backed up first, and only the world is restored. Optional: **back up automatically when the server stops**, keeping the last N automatic backups (yours are never deleted).
- **Player manager** (console → Show list): add friends to the whitelist by nickname (even before they ever joined), turn the whitelist on or off, give or remove OP, kick, ban and unban, without typing commands.
- **Crash helper**: when a server stops unexpectedly, the console says why in plain words when the log shows it (port in use, wrong Java, memory, missing mod, EULA, damaged world) with a one-click fix, and can copy the log for asking help (addresses hidden).
- **Log search and filter**: search the console, or show only warnings or errors.
- **Check before starting**: a port already in use (by another server or program) or too little memory / disk space is shown before the start, with a fix.
- **Save and restart** in the Stop ▾ menu.
- The console follows the light theme too.
### ko
- **백업 관리** (설정 → 월드 → 백업 관리): 모든 백업의 날짜·종류·크기를 보고 원하는 시점으로 **복원**해요. 지금 월드를 먼저 백업하고, 월드만 되돌려요. 선택: **서버를 끌 때 자동 백업** (최근 N개만 남기고, 직접 만든 백업은 지우지 않아요).
- **플레이어 관리** (콘솔 → 목록 보기): 닉네임으로 화이트리스트 추가(접속한 적 없어도 돼요), 화이트리스트 켜기/끄기, OP 주기·빼기, 킥, 밴·밴 풀기를 명령어 없이.
- **오류 도우미**: 서버가 예상치 못하게 꺼지면 로그에서 확인되는 원인(포트 사용 중, Java 버전, 메모리, 빠진 모드, EULA, 월드 손상)을 쉬운 말로 알려 주고 바로 고치는 버튼을 보여 줘요. 도움 요청용 로그 복사(주소는 가려요)도 있어요.
- **로그 검색과 필터**: 콘솔 검색, 경고만 / 오류만 보기.
- **시작 전 점검**: 포트가 이미 쓰이고 있거나(다른 서버·프로그램) 메모리·디스크가 부족하면 시작 전에 알려 주고 고칠 수 있게 해요.
- 중지 ▾ 메뉴에 **저장하고 재시작**.
- 밝은 테마에서 콘솔도 밝게 나와요.

## 1.25.1
### en
- Fixed: the numbers next to the console (online, uptime, total uptime) overlapped their dividers.
### ko
- 고침: 콘솔 옆 숫자(접속 중, 가동 시간, 총 가동 시간)가 구분선과 겹쳐 보이던 문제.

## 1.25.0
### en
- **After a start, the console says whether friends can join**: "The server is on. Friends elsewhere can't join yet" with a button to open it to the internet, or "Friends can join" with the address and **Copy invitation**.
- **Network tab**: the address list (This PC, Same Wi-Fi, Internet, Bedrock) marks the one to **send to friends**, and **Copy invitation** copies the game version, that address and "only while the server PC is on". The tunnel and router steps are now one section, **Open to the internet**, with a switch between **playit.gg tunnel (recommended)** and **Open a router port**.
- **New server**: name, server type, version and memory first; world and game settings are folded away. The EULA stays visible above the buttons, and a missing field is marked right where it is.
- **Plugins / Mods**: when nothing is installed yet, a short note says they're optional, with a button to find some.
- **Settings**: a bar at the bottom shows unsaved changes with **Undo changes** and **Save server settings**; the World part says its buttons run right away.
- Polish: server names use the full sidebar width, clearer arrows on drop-downs and number fields, faster tab switching, tidier console numbers.
### ko
- **서버를 켜면 콘솔이 친구 접속 상태를 알려 줘요**: "서버는 켜졌어요 · 다른 곳의 친구는 아직 못 들어와요"와 [인터넷으로 열기] 버튼, 또는 "친구가 들어올 수 있어요"와 주소, **초대 안내 복사**.
- **네트워크 탭**: 접속 주소(이 PC, 같은 와이파이, 인터넷, 베드락)에 **친구에게 보낼 주소**를 표시하고, **초대 안내 복사**로 게임 버전·그 주소·"서버 PC가 켜져 있을 때만"을 한 번에 복사해요. 터널과 공유기 설정은 **인터넷으로 열기** 한 곳으로 합치고, **playit.gg 터널 (추천)** / **공유기 포트 열기** 중에서 골라요.
- **새 서버 만들기**: 이름·서버 종류·버전·메모리만 먼저 보이고, 월드·게임 설정은 접어 뒀어요. EULA는 버튼 바로 위에 늘 보이고, 빠진 항목은 그 자리에 바로 표시해요.
- **플러그인 / 모드**: 아무것도 없을 때 "없어도 돼요" 안내와 찾기 버튼을 보여 줘요.
- **설정**: 아래쪽 바에 저장 안 한 변경과 **바꾼 내용 되돌리기**, **서버 설정 저장** 버튼이 있어요. 월드 영역에는 "누르면 바로 실행돼요" 안내를 넣었어요.
- 다듬기: 서버 이름이 사이드바 폭을 다 써요, 선택 상자·숫자 칸 화살표가 잘 보여요, 탭 전환이 빨라졌어요, 콘솔 옆 숫자를 위로 모았어요.

## 1.24.0
### en
- **No more data loss on quit or update**: servers are no longer force-stopped after 30 seconds. Bartizan waits while a big world is saving and only offers a force stop (never does it on its own).
- **Direct internet connection** (no router, the PC has a public address): the Network tab says so, no port forwarding is needed, and it tells you what to check instead. A provider-shared address (carrier NAT, phone hotspots) points you to the tunnel.
- Diagnostic info no longer shows the PC's real address when it is a public one.
- New in App settings: **start Bartizan when Windows starts**, optionally in the tray and starting a chosen server.
- The installed app offers once to move old downloaded copies (Bartizan (1).exe, ...) to the Recycle Bin.
- "What's new" is shown only once per version, also when an old copy was opened in between.
- Fixed: cancelling a world import still replaced the world.
- Fixed: Nether and End went missing when importing a Paper world into a Vanilla/Fabric/Forge server (and the other way round).
- Fixed: two backups in the same second overwrote each other; backups of a world in a sub-folder couldn't be imported.
- Fixed: a world import or upgrade could overlap with a server start.
- Fixed: mod/plugin updates now install newly required dependencies.
- Fixed: the tunnel address of another server was shown after switching servers.
- Fixed: changing the port while running closed the wrong router port at stop.
- Fixed: unsaved settings were lost when switching servers (you're now asked to save).
- Fixed: turning the whitelist off while the server runs now takes effect right away.
- Clearer failures: a plain cause with **Try again**, the create form comes back filled in, and a crash is told apart from a normal stop.
- Design: readable white text on dark-theme buttons, keyboard focus is visible, private addresses can be shown with a button, Qt dialogs (Yes/No/Cancel) in Korean, the first start follows the system language, and Korean texts use one friendly tone.
### ko
- **종료·업데이트 때 데이터 손실 방지**: 30초 뒤 서버를 강제로 끄지 않아요. 큰 월드가 저장되는 동안 기다리고, 강제 종료는 물어보기만 해요 (스스로 하지 않아요).
- **공유기 없이 인터넷에 직접 연결된 PC**: 네트워크 탭이 이를 알려 주고, 포트포워딩 없이 무엇을 확인하면 되는지 안내해요. 통신사가 나눠 쓰는 주소(통신사 NAT, 휴대폰 핫스팟)면 터널을 쓰라고 안내해요.
- 진단 정보 복사에서 이 PC 주소가 공인 IP일 때 더 이상 그대로 보이지 않아요.
- 앱 설정에 **Windows를 켜면 Bartizan 실행** 추가: 트레이에서 조용히 시작하고, 고른 서버도 같이 켤 수 있어요.
- 설치형 앱이 예전에 다운로드한 파일(Bartizan (1).exe 등)을 휴지통으로 옮길지 한 번 물어봐요.
- "새로운 기능"은 버전마다 한 번만 나와요 (중간에 예전 파일을 켰더라도).
- 고침: 월드 가져오기를 취소해도 월드가 바뀌던 문제.
- 고침: Paper 월드를 Vanilla/Fabric/Forge 서버로 가져오면 네더·엔드가 사라지던 문제 (반대 방향도).
- 고침: 같은 초에 만든 백업이 서로 덮어쓰던 문제, 하위 폴더 월드의 백업을 다시 가져오지 못하던 문제.
- 고침: 월드 가져오기·업데이트와 서버 시작이 겹칠 수 있던 문제.
- 고침: 모드·플러그인 업데이트 때 새로 필요해진 의존성도 설치해요.
- 고침: 서버를 바꿨는데 다른 서버의 터널 주소가 보이던 문제.
- 고침: 실행 중 포트를 바꾸면 중지할 때 엉뚱한 공유기 포트를 닫던 문제.
- 고침: 서버를 바꾸면 저장 안 한 설정이 사라지던 문제 (이제 저장할지 물어봐요).
- 고침: 서버 실행 중 화이트리스트를 끄면 바로 적용돼요.
- 실패 안내 개선: 쉬운 원인과 **다시 시도** 버튼, 서버 만들기에 실패하면 입력한 내용 그대로 돌아가고, 비정상 종료와 정상 중지를 구분해요.
- 디자인 개선: 다크 테마 버튼 글자 대비 개선, 키보드 포커스 표시, 가려진 주소를 버튼으로 보기, 기본 대화상자 버튼(예/아니요/취소) 한국어화, 첫 실행 때 시스템 언어 따르기, 한국어 말투 통일(~해요).

## 1.23.0
### en
- **Installer**: Bartizan now comes as `Bartizan-Setup.exe`. It installs for your user (no administrator prompt) with Start menu and desktop shortcuts, and can be removed in Windows Settings → Apps. Updates run the installer silently and restart the app.
- If you use the single `Bartizan.exe`, it offers once to switch to the installed app; your servers and worlds stay, and the old EXE is removed.
- Fewer antivirus false alarms (e.g. V3): the installed app no longer unpacks itself into a temp folder at every start, its launcher is built from source, and the files carry product, version and publisher details.
### ko
- **설치 프로그램**: 이제 `Bartizan-Setup.exe`로 설치해요. 관리자 권한 없이 내 계정에만 설치되고, 시작 메뉴·바탕화면 바로가기가 생기며, Windows 설정 → 앱에서 제거할 수 있어요. 업데이트는 설치 프로그램을 조용히 실행한 뒤 앱을 다시 켜요.
- `Bartizan.exe` 하나로 쓰고 있었다면, 한 번 설치형으로 바꿀지 물어봐요. 서버와 월드는 그대로이고, 예전 EXE는 지워져요.
- 백신(V3 등) 오진이 줄어요: 설치형은 실행할 때마다 임시 폴더에 압축을 풀지 않고, 실행 부분(부트로더)을 직접 빌드하고, 파일에 제품명·버전·제작자 정보를 넣었어요.

## 1.22.1
### en
- Stop is never a dead button any more: pressing it while the server is still starting or already stopping sends "stop" again, the console says what's happening ("saving the world..."), and if the server is still running a minute later you're offered a force stop.
- Also includes everything from 1.22.0 below.
### ko
- 중지 버튼이 먹히지 않던 문제: 서버가 아직 켜지는 중이거나 이미 멈추는 중일 때 눌러도 "stop"을 다시 보내요. 콘솔에 지금 상황("월드를 저장하고 있어요...")을 보여주고, 1분이 지나도 안 꺼지면 강제 종료할지 물어봐요.
- 아래 1.22.0의 변경 사항도 모두 들어 있어요.

## 1.22.0
### en
- New: **Copy diagnostic info** in the Network tab checks the router, double NAT, firewall, tunnel and ports, and copies a summary to paste into a chat (internet addresses are partly hidden).
- Fixed: Bartizan could silently refuse to start when the Documents folder is synced with OneDrive between two PCs (the "already running" lock came from the other PC). If another copy really is running, it now says so.
- Fixed: a world folder name (level-name) like "." or ".." made "New world" or "Import world" delete the server folder, or every server, including backups. Such names are now refused.
- Fixed: quitting while the "No internet" question was open started the server anyway.
- Tunnel: with several tunnels, the one for this server's port is shown, and an address you typed in is kept.
### ko
- 새 기능: 네트워크 탭의 **진단 정보 복사**가 공유기, 이중 NAT, 방화벽, 터널, 포트를 확인하고 결과를 복사해요. 채팅에 붙여넣어 보내면 돼요 (인터넷 주소는 일부 가려져요).
- 수정: 문서 폴더를 OneDrive로 두 PC에서 동기화하면 Bartizan이 아무 말 없이 실행되지 않던 문제 (다른 PC의 "실행 중" 표시를 보고 멈췄어요). 정말 이미 실행 중이면 그렇다고 알려줘요.
- 수정: 월드 폴더 이름(level-name)이 "."이나 ".." 같으면 "새 월드"나 "월드 불러오기"가 서버 폴더(또는 모든 서버)를 백업까지 지울 수 있던 문제. 이런 이름은 이제 거부해요.
- 수정: "인터넷 없음" 질문이 떠 있을 때 앱을 종료하면 서버가 켜지던 문제.
- 터널: 터널이 여러 개면 이 서버 포트에 맞는 주소를 보여주고, 직접 입력한 주소는 덮어쓰지 않아요.

## 1.21.0
### en
- Manual port forwarding ("If automatic doesn't work") now finds your router for you: its real address (the default gateway), its brand and model when it tells us, and where its settings page actually answers (some only work on https or a port like :8080 / :8899).
- "Open the router page" opens that address directly, and the steps show the menu for common routers (ipTIME, KT, SK broadband, LG U+, ASUS, TP-Link, NETGEAR).
- Warns when there's another router or the provider's modem in front (double NAT / carrier NAT), where forwarding on this router alone can't work.
- "Check the port from outside" confirms that friends can reach the server after you set it up.
### ko
- 직접 포트포워딩("자동으로 안 될 때")에서 공유기를 자동으로 찾아줘요: 실제 공유기 주소(기본 게이트웨이), 알 수 있으면 제조사와 모델, 그리고 설정 페이지가 실제로 응답하는 주소(https나 :8080, :8899 같은 포트로만 열리는 기기도 있어요).
- "공유기 설정 페이지 열기"가 그 주소를 바로 열고, 흔한 공유기(ipTIME, KT, SK브로드밴드, LG U+, ASUS, TP-Link, NETGEAR)는 메뉴 위치도 알려줘요.
- 앞에 다른 공유기나 통신사 모뎀이 있어서(이중 NAT / CGNAT) 이 공유기만으로는 포트포워딩이 안 되는 경우를 알려줘요.
- "바깥에서 포트 확인"으로 설정 후 친구가 실제로 들어올 수 있는지 확인할 수 있어요.

## 1.20.0
### en
- Tunnel: the tunnel address now fills in by itself. The playit agent doesn't print it, so Bartizan asks playit.gg for this PC's tunnels. If there's no Minecraft Java tunnel yet, the Network tab says how to add one.
- Server status no longer says "not reachable from the internet" while friends can join through the tunnel, and a fresh tunnel that the outside check hasn't seen yet shows as "not confirmed yet" instead of an error.
- Updates now replace Bartizan.exe in place: the new version is downloaded to a temporary folder, waits for the app to close, copies itself over Bartizan.exe and starts it. No more .new / .old files next to the app.
### ko
- 터널: 터널 주소가 이제 자동으로 채워져요. playit 프로그램이 주소를 출력하지 않아서, Bartizan이 playit.gg에 이 PC의 터널을 직접 물어봐요. 아직 Minecraft Java 터널이 없으면 네트워크 탭에서 추가 방법을 알려줘요.
- 친구가 터널로 들어올 수 있는데도 서버 상태에 "인터넷에서 접속할 수 없어요"라고 나오던 문제를 고쳤어요. 막 만든 터널을 외부 확인 서비스가 아직 못 봤을 때는 오류 대신 "아직 확인되지 않음"으로 보여줘요.
- 업데이트가 이제 Bartizan.exe 하나만 바꿔요: 새 버전을 임시 폴더에 받고, 앱이 닫히면 Bartizan.exe를 덮어쓴 뒤 다시 실행해요. 앱 옆에 .new / .old 파일이 더 이상 생기지 않아요.

## 1.19.1
### en
- Fixed: the playit.gg tunnel stopped right away with "code 2". playit 1.0 changed its download to a background service that doesn't take the same settings; Bartizan now uses playit's standalone agent 0.17.1 (still supported by playit) and replaces a wrong download automatically.
- Quitting while something is still loading in the background (e.g. the update check) no longer shows an error box or risks a crash.
### ko
- 수정: playit.gg 터널이 "코드 2"로 바로 멈추던 문제. playit 1.0부터 받는 파일이 다른 방식의 백그라운드 서비스로 바뀌어서 실행 설정을 알아듣지 못했어요. 이제 playit이 계속 지원하는 단독 실행 버전 0.17.1을 쓰고, 잘못 받은 파일은 자동으로 바꿔요.
- 백그라운드 작업(예: 업데이트 확인)이 남아 있을 때 앱을 종료해도 오류 창이 뜨거나 오류로 꺼지지 않아요.

## 1.19.0
### en
- Network tab is much quieter: explanations moved into (?) buttons next to each section title.
- The Tunnel (?) explains step by step how to set up playit.gg.
- "If automatic doesn't work" (manual port forwarding) is folded away; press ▾ to open it.
- Private addresses fade in and out of the blur smoothly when clicked.
### ko
- 네트워크 탭의 글을 줄였어요. 설명은 각 제목 옆 (?) 버튼 안으로 옮겼어요.
- 터널 (?)에 playit.gg 설정 방법을 단계별로 적었어요.
- "자동으로 안 될 때"(직접 포트포워딩) 안내는 접혀 있어요. ▾를 누르면 펼쳐져요.
- 가려진 주소를 누르면 블러가 부드럽게 걷히고 다시 덮여요.

## 1.18.1
### en
- Fixed: the EXE didn't start ("No module named 'PySide6.QtNetwork'"). The build left out a Qt part the app needs; it's included again, and the app now starts even without it.
- The release build is now checked by actually starting the app, so this can't slip through again.
### ko
- 수정: EXE가 실행되지 않던 문제 ("No module named 'PySide6.QtNetwork'"). 빌드에서 앱에 필요한 Qt 모듈이 빠져 있었어요. 다시 넣었고, 혹시 빠져도 앱은 켜지게 했어요.
- 이제 배포 전에 앱을 실제로 켜 보고 확인해서, 같은 문제가 다시 생기지 않아요.

## 1.18.0
### en
**Windows Firewall**
- *Allow in Windows Firewall* now also allows Java itself and removes the block rules Windows makes when someone presses *Cancel* in its first-run popup (a block rule beats every allow rule).
- The Network tab shows whether the firewall lets players in, and *Server status* no longer says "Same Wi-Fi: OK" when the firewall actually blocks other devices.

**Fixes**
- Deleting a server and creating a new one with the same name no longer shows the old log, graphs or unsaved settings.
- The tunnel and the router port are only started once Java really runs; a port opened while the server was stopping is closed again.
- server.properties lines with some Korean (cp949) or special characters are no longer split on save.
- World import works with a level name in a subfolder (e.g. worlds/main).
- Cancel works while the Forge/NeoForge installer is quiet; its files are removed after a failure.
- Java install: retries when antivirus holds the new files, and keeps the old Java if replacing fails.
- Snapshots are ordered by their real release dates; settings, uptime and player lists are saved safely.
### ko
**Windows 방화벽**
- *Windows 방화벽 허용*이 이제 Java 자체도 허용하고, 처음 뜨는 Windows 창에서 *취소*를 눌렀을 때 생긴 차단 규칙도 지워요 (차단 규칙은 허용 규칙보다 우선이에요).
- 네트워크 탭에 방화벽이 플레이어를 들여보내는지 표시돼요. 방화벽이 다른 기기를 막고 있으면 *서버 상태*에서 "같은 와이파이: 접속 가능"이라고 잘못 나오지 않아요.

**버그 수정**
- 서버를 지우고 같은 이름으로 새로 만들면 예전 로그, 그래프, 저장 안 한 설정이 보이던 문제를 고쳤어요.
- 터널과 공유기 포트는 Java가 실제로 켜진 뒤에만 열어요. 서버가 꺼지는 사이에 열린 포트는 다시 닫아요.
- 일부 한글(cp949)이나 특수 문자가 든 server.properties 줄이 저장할 때 쪼개지지 않아요.
- 월드 이름이 하위 폴더(예: worlds/main)여도 월드 불러오기가 제대로 돼요.
- Forge/NeoForge 설치 프로그램이 조용할 때도 취소가 돼요. 실패하면 설치 파일을 지워요.
- Java 설치: 백신이 새 파일을 잡고 있으면 다시 시도하고, 교체에 실패하면 예전 Java를 그대로 둬요.
- 스냅샷 버전을 실제 출시일 순서로 정렬해요. 설정, 가동 시간, 플레이어 목록을 안전하게 저장해요.

## 1.17.0
### en
**Design**
- Cleaner, calmer look: sections are a title over a thin line instead of boxes, neutral greys, smaller corners, no emoji.
- The logo blue is kept for the main buttons, the selected tab and server, and switches. The **Stop** button is now red.
- The header shows one quiet line: "● Running · Paper 1.21.4 · Memory 2 GB".
- Fewer (?) buttons: most explanations are now a short gray line under the setting.
- Switching tabs, servers or pages now blends the old screen into the new one instead of fading in from dark.

**Faster**
- The console no longer redraws its whole log when you come back to it or save settings, and handles log floods much faster.
- Live numbers, graphs and join checks pause while the window is minimized.
- Plugin/mod switches and the Modrinth search no longer re-read every installed jar each time.

**Fixes**
- Unsaved Settings edits and the Status graphs are kept when the window reloads (rename, app settings...).
- Saving Settings no longer changes untouched memory values (e.g. 1.5 GB).
- A failed world import no longer deletes the current world; backups work with very old file dates.
- A software switch that fails halfway no longer leaves a server that can't start; mod world types are kept on updates.
- Server duplicates keep plugin data folders; settings files keep their text encoding and are written safely.
- Cancelled downloads leave no half files; Geyser updates keep the old version if the download fails.
- The playit.gg tunnel can't start twice or after you stopped it during the download.
- Ports opened automatically (UPnP) are closed again when the server stops.
- Quitting or shutting Windows down with servers running stops them with a save; several hung servers no longer freeze the app for minutes.
- Other small fixes (chat can't fake a player's IP, Start button after the offline prompt, snapshot/release-candidate ordering...).
### ko
**디자인**
- 더 깔끔하고 차분하게: 상자 대신 제목과 얇은 선으로 구역을 나누고, 중립 회색과 작은 모서리를 쓰고, 이모지를 뺐어요.
- 로고 파란색은 주요 버튼, 선택된 탭과 서버, 스위치에만 써요. **중지** 버튼은 빨간색이 됐어요.
- 위쪽에 "● 실행 중 · Paper 1.21.4 · 메모리 2 GB" 한 줄로 보여줘요.
- (?) 버튼을 줄였어요. 대부분의 설명은 설정 아래 회색 글 한 줄로 바뀌었어요.
- 탭·서버·화면을 바꿀 때 어두워졌다 나타나지 않고, 이전 화면에서 새 화면으로 자연스럽게 겹쳐 넘어가요.

**더 빨라졌어요**
- 콘솔로 돌아오거나 설정을 저장할 때 로그 전체를 다시 그리지 않고, 로그가 쏟아질 때도 훨씬 빨라요.
- 창을 최소화하면 실시간 수치, 그래프, 접속 확인을 멈춰요.
- 플러그인/모드 켜기·끄기와 Modrinth 검색이 매번 모든 jar를 다시 읽지 않아요.

**버그 수정**
- 창이 새로 고쳐져도(이름 바꾸기, 앱 설정 등) 저장 안 한 설정과 서버 상태 그래프가 그대로 남아요.
- 설정을 저장해도 건드리지 않은 메모리 값(예: 1.5GB)은 바뀌지 않아요.
- 월드 불러오기가 실패해도 지금 월드가 지워지지 않아요. 아주 오래된 날짜의 파일이 있어도 백업돼요.
- 구동기 바꾸기가 중간에 실패해도 서버가 안 켜지는 일이 없어요. 업데이트할 때 모드 월드 유형이 유지돼요.
- 서버 복제 시 플러그인 데이터 폴더가 빠지지 않아요. 설정 파일은 원래 인코딩을 유지하고 안전하게 저장돼요.
- 다운로드를 취소해도 반쪽 파일이 남지 않아요. Geyser 업데이트 다운로드가 실패하면 예전 버전이 남아 있어요.
- playit.gg 터널이 두 번 켜지거나, 다운로드 중에 중지했는데 켜지는 문제를 고쳤어요.
- 자동으로 연 포트(UPnP)는 서버가 꺼지면 다시 닫아요.
- 서버가 켜진 채로 종료하거나 Windows를 끄면 저장 후 서버를 꺼요. 응답 없는 서버가 여러 개여도 앱이 몇 분씩 멈추지 않아요.
- 그 밖의 작은 수정 (채팅으로 플레이어 IP를 속일 수 없게, 오프라인 안내 후 시작 버튼, 스냅샷/RC 버전 순서 등).

## 1.16.0
### en
- New colours taken from the Bartizan logo: the blue of the logo is the main colour, and greys lean slightly blue. Green now only means "running / reachable".
- Cleaner look: rounder cards, quieter section titles and borders, blue selection highlights.
### ko
- Bartizan 로고에서 가져온 새 색상: 로고의 파란색을 대표 색으로 쓰고, 회색도 살짝 푸른 톤으로 맞췄어요. 초록색은 이제 "실행 중 / 접속 가능"만 뜻해요.
- 더 깔끔한 디자인: 둥근 카드, 차분한 제목과 테두리, 파란 선택 표시.

## 1.15.0
### en
- **Switch server software**: Settings → World → *Server version* → *Software* turns an existing server into Paper, Purpur, Vanilla, Fabric, NeoForge or Forge. The world and settings stay, a full backup is made first, and the Nether/End are moved where the new software expects them.
- The Settings tab is now the last tab.
### ko
- **구동기 바꾸기**: 설정 → 월드 → *서버 버전* → *구동기*에서 기존 서버를 Paper, Purpur, Vanilla, Fabric, NeoForge, Forge로 바꿀 수 있어요. 월드와 설정은 그대로이고, 먼저 서버 전체를 백업하고, 네더·엔드도 새 구동기에 맞는 자리로 옮겨요.
- 설정 탭을 맨 마지막으로 옮겼어요.

## 1.14.0
### en
- Header: *Force stop* moved into the ▾ menu next to *Stop*; the folder button is gone (use 📁 Folder in the sidebar).
- Console: Online, Uptime and Total uptime split the side panel into three equal parts.
- The World tab is now part of the Settings tab (world, server version, import and backups at the bottom).
- The Players tab is removed. Use console commands such as `op <name>` or `whitelist add <name>`.
### ko
- 위쪽 버튼: *강제 종료*는 *중지* 옆 ▾ 메뉴 안으로 옮겼어요. 폴더 버튼은 없앴어요 (왼쪽 아래 📁 폴더를 쓰세요).
- 콘솔: 접속 중 · 가동 시간 · 총 가동 시간을 오른쪽에 똑같이 삼등분해서 보여줘요.
- 월드 탭을 설정 탭 안으로 옮겼어요 (아래쪽에 월드, 서버 버전, 불러오기, 백업).
- 플레이어 탭을 없앴어요. 콘솔에서 `op 이름`, `whitelist add 이름` 같은 명령어를 쓰세요.

## 1.13.0
### en
- **Auto-save**: Settings tab → *Auto-save* saves the world every 5, 10, 15, 30 or 60 minutes while the server runs.
- The console's *Send* button is gone; press Enter to send a command.
### ko
- **자동 저장**: 설정 탭 → *자동 저장*에서 고른 간격(5·10·15·30분, 1시간)마다 서버가 켜져 있는 동안 월드를 저장해요.
- 콘솔의 *보내기* 버튼을 없앴어요. 명령어는 Enter로 보내요.

## 1.12.7
### en
- Plugin/mod on/off switches slide smoothly.
- Network tab: click a blurred address to show it, click it again to blur it (the 👁 button is gone).
### ko
- 플러그인/모드 켜기·끄기 스위치가 부드럽게 움직여요.
- 네트워크 탭: 흐린 주소를 누르면 보이고, 한 번 더 누르면 다시 가려져요 (👁 버튼은 없앴어요).

## 1.12.6
### en
- The (?) next to Description is gone. The colour codes still show when you hover over the description box.
### ko
- 설명 옆의 (?)를 없앴어요. 색 코드 안내는 설명 칸에 마우스를 올리면 보여요.

## 1.12.5
### en
- Hidden addresses in the Network tab are now blurred instead of replaced with •••. Click 👁 to show them.
### ko
- 네트워크 탭에서 가린 주소를 ••• 대신 흐리게(블러) 처리해요. 👁을 누르면 보여요.

## 1.12.4
### en
- Network tab: your Wi-Fi IP, internet IP, Bedrock and tunnel addresses are hidden (•••) until you click the 👁 button next to them — handy when streaming or sharing your screen. *Copy* still copies the real address.
### ko
- 네트워크 탭: 와이파이 IP, 인터넷 IP, 베드락·터널 주소를 기본으로 가려요(•••). 옆의 👁 버튼을 누르면 보여요. 방송이나 화면 공유할 때 좋아요. *복사*는 그대로 실제 주소를 복사해요.

## 1.12.3
### en
Bug fixes from a full review:
- Only one copy of the app runs; opening it again brings back the running window instead of starting the same server twice.
- Fixed a crash when quitting while a network check was still running, and after an app update restarted.
- While a server starts, it now counts as running: Stop works, and the world can't be replaced mid-start.
- Korean chat in the console no longer turns into "���"; chat can't fake players joining or leaving.
- Plugin/mod updates while the server runs no longer leave two versions behind; locked files show a clear message and the on/off switch flips back.
- Cut-off downloads are rejected instead of saved; slow or odd network answers no longer cause errors.
- Tunnel: the Bedrock address no longer replaces the Java one; an agent that can't start shows an error instead of "Starting..." forever.
- UPnP works with a VPN active; repeated firewall clicks no longer pile up rules.
- Settings: changing the icon keeps unsaved edits; Save only writes what you changed.
- Server status: numbers keep updating after saving settings; the port status and disk size don't carry over to another server.
- Importing a backup keeps the Nether and End; cancelled backups are removed; a broken ops.json is never wiped.
- Updating Bedrock support no longer deletes other plugins whose names start with "Geyser".
- start.bat works with non-English folder names; server.properties with a BOM is read correctly.
- Snapshot servers are offered updates; offline, the Update button says the list didn't load.
### ko
전체 점검에서 찾은 버그를 고쳤어요:
- 앱은 하나만 실행돼요. 다시 열면 같은 서버가 두 번 켜지는 대신 실행 중인 창이 나타나요.
- 네트워크 확인 중에 종료하거나 앱 업데이트 후 다시 시작할 때 꺼지던 문제를 고쳤어요.
- 서버가 켜지는 중에도 실행 중으로 취급해요. 중지할 수 있고, 켜는 도중에 월드를 바꿀 수 없어요.
- 콘솔에서 한글 채팅이 "���"로 깨지지 않아요. 채팅으로 접속/퇴장을 꾸밀 수 없어요.
- 서버 실행 중 플러그인/모드를 업데이트해도 두 버전이 남지 않아요. 파일이 잠겨 있으면 알려주고 스위치도 원래대로 돌아가요.
- 중간에 끊긴 다운로드는 저장하지 않아요. 느리거나 이상한 네트워크 응답에도 오류가 나지 않아요.
- 터널: 베드락 주소가 자바 주소를 덮어쓰지 않아요. 에이전트가 시작되지 않으면 계속 "시작 중"이 아니라 오류를 보여줘요.
- VPN을 켜도 UPnP가 작동해요. 방화벽 버튼을 여러 번 눌러도 규칙이 쌓이지 않아요.
- 설정: 아이콘을 바꿔도 저장 안 한 입력이 남아요. 저장하면 바꾼 것만 기록해요.
- 서버 상태: 설정 저장 후에도 수치가 계속 갱신돼요. 포트 상태와 디스크 크기가 다른 서버로 넘어가지 않아요.
- 백업을 불러오면 네더와 엔드도 함께 와요. 취소한 백업은 지워져요. 깨진 ops.json을 덮어쓰지 않아요.
- 베드락 업데이트 시 이름이 "Geyser"로 시작하는 다른 플러그인을 지우지 않아요.
- 한글 폴더에서도 start.bat이 작동해요. BOM이 있는 server.properties도 제대로 읽어요.
- 스냅샷 서버에도 업데이트가 보여요. 오프라인이면 업데이트 버튼이 목록을 못 불러왔다고 알려줘요.

## 1.12.2
### en
- Before your first server, the app shows only the welcome page in the middle — no empty sidebar. The sidebar fades in once a server exists. App settings are reachable from the welcome page.
### ko
- 첫 서버를 만들기 전에는 왼쪽 창 없이 가운데 시작 화면만 보여줘요. 서버를 만들면 왼쪽 창이 부드럽게 나타나요. 앱 설정은 시작 화면에서도 열 수 있어요.

## 1.12.1
### en
- Back to the previous layout (tabs, header buttons and Settings as in 1.11). The Home tab is removed.
- Kept the smooth transitions: tabs, server switches and dialogs fade in. Low-resource mode turns them off.
### ko
- 이전 디자인으로 되돌렸어요 (탭, 위쪽 버튼, 설정 탭이 1.11과 같아요). 홈 탭은 없앴어요.
- 자연스러운 전환 효과는 그대로 있어요: 탭, 서버 전환, 창이 부드럽게 나타나요. 저사양 모드에서는 꺼져요.

## 1.12.0
### en
- **Simpler design for beginners**: a new **Home** tab shows whether the server is on, one big Start/Stop button, the addresses to join with (with Copy buttons) and first-time steps.
- Tabs are reordered with icons (everyday ones first), and *Network* is now **Invite friends**.
- One Start/Stop button in the header; *Open server folder* and *Force stop* moved into the ⋯ menu.
- Settings shows the basics first; port, distances, online mode and the like are under **Advanced settings**.
- Smooth transitions: pages, servers and dialogs fade in, and Advanced settings slides open. Low-resource mode turns them off.
### ko
- **초보자도 쉬운 디자인**: 새 **홈** 탭에서 서버가 켜져 있는지, 큰 켜기/끄기 버튼, 접속 주소(복사 버튼 포함), 처음 하는 방법을 한눈에 볼 수 있어요.
- 탭 순서를 자주 쓰는 것부터 정리하고 아이콘을 붙였어요. *네트워크*는 **친구 초대**로 이름을 바꿨어요.
- 위쪽에는 켜기/끄기 버튼 하나만 두고, *서버 폴더 열기*와 *강제 종료*는 ⋯ 메뉴로 옮겼어요.
- 설정 탭은 기본 설정만 먼저 보여주고, 포트·거리·정품 인증 같은 건 **고급 설정**에 모았어요.
- 자연스러운 전환 효과: 화면, 서버, 창이 부드럽게 나타나고 고급 설정은 미끄러지듯 열려요. 저사양 모드에서는 꺼져요.

## 1.11.0
### en
- **Find more plugins and mods**: Plugins/Mods tab → *Find more* searches Modrinth and installs with one click. Only versions made for your server's software and Minecraft version are shown, and required add-ons (like Fabric API) come along automatically.
- **Check for updates** in the Plugins/Mods tab finds newer versions of plugins and mods that came from Modrinth and updates them all at once.
- Mods that players also have to install are marked "Players need it too".
### ko
- **플러그인·모드 찾아보기**: 플러그인/모드 탭 → *더 찾아보기*에서 Modrinth를 검색하고 버튼 한 번으로 설치해요. 이 서버의 구동기와 마인크래프트 버전에 맞는 것만 보여주고, 꼭 필요한 다른 모드(예: Fabric API)도 같이 설치돼요.
- 플러그인/모드 탭의 **업데이트 확인**으로 Modrinth에서 받은 플러그인·모드의 새 버전을 찾아 한 번에 업데이트해요.
- 접속하는 사람도 설치해야 하는 모드에는 "플레이어도 설치 필요"라고 표시해요.

## 1.10.0
### en
- **Total uptime**: the console now shows how long the server has run in total, across every start, under the current uptime.
### ko
- **총 가동 시간**: 콘솔의 가동 시간 아래에 지금까지 서버를 켜 둔 시간을 모두 더한 총 가동 시간이 나와요.

## 1.9.1
### en
- The server preview shows Minecraft's default server icon instead of "No icon" when you haven't picked one, just like in the game's server list.
### ko
- 아이콘을 고르지 않았을 때 미리보기에 "아이콘 없음" 대신, 게임 서버 목록처럼 마인크래프트 기본 서버 아이콘을 보여줘요.

## 1.9.0
### en
- **Server version moved into the World tab**: updating the server version and reinstalling Java are now in World → *Server version*.
- **(?) help buttons**: long explanations are tucked behind a small (?) next to each setting — click it to read more. Screens are shorter and easier to scan.
- **Spawn protection** can be changed in the Settings tab.
- New servers start with spawn protection off (everyone can build at spawn) and no kicking for chatting or typing commands fast (Minecraft 26.2+).
- Korean text is easier to read: a Korean font is used first, and the wording is more consistent.
### ko
- **서버 버전을 월드 탭으로 옮겼습니다**: 서버 버전 업데이트와 Java 다시 설치는 이제 월드 → *서버 버전*에 있어요.
- **(?) 도움말 버튼**: 긴 설명은 설정 옆의 작은 (?)를 누르면 볼 수 있어요. 화면이 짧아지고 한눈에 보기 쉬워졌어요.
- 설정 탭에서 **스폰 보호** 범위를 바꿀 수 있어요.
- 새 서버는 스폰 보호가 꺼져 있고(스폰에서 누구나 건축 가능), 채팅·명령어를 빨리 쳐도 추방하지 않아요(마인크래프트 26.2 이상).
- 한국어 가독성 개선: 한글 글꼴을 먼저 쓰고, 문장 말투를 통일했어요.

## 1.8.0
### en
- **Play without internet**: starting a server with no internet now offers *Start in offline mode*, so players on this PC or the same Wi-Fi can join instead of getting "Authentication servers are down". Online mode turns back on by itself when the server stops.
- The Bartizan icon inside the app is now sharp instead of jagged, including on 125–200% display scaling.
### ko
- **인터넷 없이 플레이**: 인터넷이 없을 때 서버를 시작하면 *오프라인 모드로 시작*을 고를 수 있습니다. 이 PC나 같은 와이파이에서 "인증 서버에 현재 연결할 수 없습니다" 없이 접속할 수 있고, 서버를 끄면 정품 인증이 자동으로 다시 켜집니다.
- 앱 안의 Bartizan 아이콘이 깨져 보이던 문제를 고쳤습니다 (화면 배율 125~200% 포함).

## 1.7.2
### en
- Fixed a crash on startup ("OverflowError") when a number in server.properties, such as max-players, was too large. Out-of-range values are now adjusted to the allowed range.
- The settings editor now refuses numbers that are too large, and if part of a server's settings can't be loaded, the app shows a warning instead of closing.
### ko
- server.properties의 숫자(예: max-players)가 너무 클 때 실행하자마자 꺼지던 문제("OverflowError")를 고쳤습니다. 범위를 벗어난 값은 허용 범위로 맞춰집니다.
- 설정 편집 창에서 너무 큰 숫자는 저장되지 않으며, 서버 설정 일부를 불러오지 못해도 앱이 꺼지지 않고 경고를 보여줍니다.

## 1.7.1
### en
- Fixed windows not fitting on screen with Windows display scaling (125–150%): the main window, New server dialog and settings editor now size themselves to the screen, so no buttons end up off-screen.
- Long server names are shortened with "…" instead of pushing buttons out of view.
### ko
- Windows 화면 배율(125~150%)에서 창이 화면 밖으로 넘치던 문제를 고쳤습니다. 메인 창, 새 서버 창, 설정 편집 창이 화면 크기에 맞춰져 버튼이 화면 밖으로 나가지 않습니다.
- 긴 서버 이름은 "…"으로 줄여 표시해 버튼이 밀려나지 않습니다.

## 1.7.0
### en
- **New name: Bartizan**, with a new icon.
- The EXE is now `Bartizan.exe` and your data moves to `Documents/Bartizan` automatically (servers, Java and settings come along).
### ko
- **새 이름: Bartizan**, 새 아이콘.
- 실행 파일 이름이 `Bartizan.exe`로 바뀌고, 데이터는 `문서/Bartizan`으로 자동으로 옮겨집니다 (서버, Java, 설정 모두 그대로).

## 1.6.0
### en
- **App updates**: ⚙ Settings → *Check for updates* downloads the newest version from GitHub and restarts the app. You'll see what's new before updating.
- The app checks for updates once a day and tells you what was added.
- "What's new" is shown once after an update.
- Starting a server without internet now warns that premium players can't sign in until the connection is back.
### ko
- **앱 업데이트**: ⚙ 설정 → *업데이트 확인*을 누르면 GitHub에서 최신 버전을 받아 앱을 다시 시작합니다. 업데이트 전에 새 기능을 보여줍니다.
- 하루에 한 번 새 버전이 있는지 확인하고, 무엇이 추가됐는지 알려줍니다.
- 업데이트 후 처음 실행할 때 "새로운 기능"을 한 번 보여줍니다.
- 인터넷 없이 서버를 시작하면, 연결될 때까지 정품 플레이어가 로그인할 수 없다고 콘솔에 알려줍니다.

## 1.5.0
### en
- Server list: ⋯ menu to rename, duplicate or move a server to the Recycle Bin.
- Server status: "Can players join?" check for this PC, Wi-Fi, internet, tunnel and Bedrock.
- Memory saver per server (Settings tab).
- Easier to read: larger text, stronger contrast, roomier forms.
### ko
- 서버 목록: ⋯ 메뉴에서 이름 바꾸기, 복제, 휴지통으로 이동.
- 서버 상태: 이 PC / 와이파이 / 인터넷 / 터널 / 베드락 "접속 가능 여부" 확인.
- 서버별 메모리 절약 (설정 탭).
- 가독성 개선: 더 큰 글자, 더 진한 대비, 넓은 입력칸.

## 1.4.0
### en
- Plugins / Mods tab: drag .jar files in, turn each one on or off.
- playit.gg tunnel: friends join without port forwarding.
- Korean translation reviewed.
### ko
- 플러그인 / 모드 탭: .jar 파일을 끌어다 놓고, 하나씩 켜고 끌 수 있습니다.
- playit.gg 터널: 포트포워딩 없이 친구가 접속할 수 있습니다.
- 한국어 번역 다듬기.

## 1.3.0
### en
- Data moved to Documents/MC-Server-Maker-Files.
- Server status tab, full server.properties editor, low-resource mode, tray icon.
### ko
- 데이터 위치를 문서/MC-Server-Maker-Files로 옮겼습니다.
- 서버 상태 탭, server.properties 전체 편집, 저사양 모드, 트레이 아이콘.

## 1.2.0
### en
- English UI with Korean option, light theme, Bedrock join (Geyser + Floodgate), NeoForge.
### ko
- 영어 기본 + 한국어 선택, 밝은 테마, 베드락 접속(Geyser + Floodgate), NeoForge.

## 1.1.0
### en
- New design, console, UPnP port opening, Windows EXE.
### ko
- 새 디자인, 콘솔, UPnP 포트 열기, Windows EXE.

## 1.0.0
### en
- First version: create servers, edit name / description / icon, worlds, updates.
### ko
- 첫 버전: 서버 만들기, 이름 / 설명 / 아이콘 편집, 월드, 업데이트.
