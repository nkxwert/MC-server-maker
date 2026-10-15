# Changelog

Each version has an English and a Korean list. The release workflow publishes the section for the
current version as the GitHub Release notes, and the app shows it as "What's new".

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
