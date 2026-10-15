# Changelog

Each version has an English and a Korean list. The release workflow publishes the section for the
current version as the GitHub Release notes, and the app shows it as "What's new".

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
