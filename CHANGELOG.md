# Changelog

Each version has an English and a Korean list. The release workflow publishes the section for the
current version as the GitHub Release notes, and the app shows it as "What's new".

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
