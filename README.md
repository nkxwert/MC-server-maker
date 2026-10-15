# MC Server Maker

Create and manage Minecraft servers with a few clicks. Windows / macOS / Linux.
English by default; switch to 한국어 in **⚙ Settings**. (한국어는 왼쪽 아래 ⚙ 설정에서 바꿀 수 있어요.)

## Download (EXE)

GitHub **Actions → Build EXE → latest run → Artifacts → `MC-Server-Maker-windows`** contains `MC-Server-Maker.exe`.
Pushing a tag such as `v1.2.0` also publishes it under **Releases**.

- All data lives in **Documents/MC-Server-Maker-Files**: `servers/<each server>/` (its files and settings), `runtime/` (Java), `settings.json`.
  Data that older versions left next to the EXE (e.g. on the Desktop) is moved there automatically.
- If Windows SmartScreen warns, click **More info → Run anyway** (the EXE isn't code-signed).

## Run from source

1. Install [Python 3.10+](https://www.python.org/downloads/) (Windows: tick **Add Python to PATH**).
2. Run `run.bat` (Windows) or `./run.sh` (macOS / Linux). The first run installs PySide6 into `.venv`.

## Features

**New server**
- Software: Paper (recommended), Vanilla, Purpur, Fabric, **NeoForge**, Forge — version lists come live from each official API, newest first.
- RAM, **automatic Java install** (on by default; Temurin 8/17/21/25 into `runtime/`).
- World: random, from seed (🎲), or import an existing world (folder or zip); world type.
- Optional **Bedrock join** (Paper/Purpur): installs Geyser + Floodgate.

**Manage**
| Tab | |
|---|---|
| Console | Colored log, command input (↑↓ history), save world, online count (**More…** → kick / ban), uptime |
| Status | CPU %, memory used / allowed, download / upload, average player ping, disk size — with live graphs |
| Settings | Name, MOTD with color preview, icon (any image → 64×64), game settings, RAM, **edit every server.properties key**, **Bedrock join on/off** |
| World | Seed info, new world (random/seed), import world, backups (automatic before replacing) |
| Players | OPs and whitelist |
| Network | Addresses (this PC / Wi-Fi / Internet / Bedrock), **one-click port opening (UPnP)**, Windows Firewall rule, manual port-forwarding guide |
| Update | Update to a newer version with a full backup first; Geyser is updated too |

**App settings (⚙)**: Dark / Light theme, English / 한국어, **Low-resource mode** (on by default).

**Low-resource mode** keeps the PC responsive while servers run: servers start with a small heap that grows
only when needed and give unused memory back (Java 17+), run at below-normal priority, and the app batches
console drawing and stops live updates while hidden. Closing the window can keep servers running from the tray.
Vanilla/Paper 1.21.2+ also pause the world when nobody is online (`pause-when-empty-seconds`).

### Playing with friends in other homes
1. **Network** tab → **Open port automatically (UPnP)**.
2. On Windows, also click **Allow in Windows Firewall**.
3. Send friends the **Internet** address (Bedrock players: the Bedrock address and port).

If UPnP is off in your router, forward the port manually (the tab shows the exact ports and your PC's IP).
Behind carrier NAT (the app detects it) use a tunnel such as [playit.gg](https://playit.gg).

## Development

```
pip install -r requirements.txt
python -m mc_server_maker                        # run
python -m unittest discover tests                # tests (no network needed)
pip install pyinstaller && python build_exe.py   # build into dist/
```

| File | |
|---|---|
| `mc_server_maker/core/providers.py` | Version lists / install per software (Mojang, PaperMC Fill v3, Purpur, Fabric meta, NeoForge & Forge maven) |
| `mc_server_maker/core/java.py` | Find Java / install from Adoptium |
| `mc_server_maker/core/server.py` | Create, update, worlds, backups, launch command |
| `mc_server_maker/core/plugins.py` | Bedrock support (Geyser + Floodgate) |
| `mc_server_maker/core/network.py` | Public IP, UPnP, firewall |
| `mc_server_maker/core/stats.py` | CPU / memory / network / disk / ping sampling |
| `mc_server_maker/core/property_catalog.py` | Every server.properties key with defaults and descriptions |
| `mc_server_maker/core/properties.py` | `server.properties` read/write (keeps comments and order) |
| `mc_server_maker/i18n.py`, `i18n_ko.py` | Translations (English source → Korean) |
| `mc_server_maker/gui/` | PySide6 UI |

> Spigot isn't offered because it must be compiled with BuildTools; Spigot plugins run on Paper.
