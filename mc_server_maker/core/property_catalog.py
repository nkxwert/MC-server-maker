"""Every vanilla server.properties setting, with its default and a short explanation.

Used by the "Edit all server.properties" dialog so settings show up even before the
server has written them. Keys a server doesn't know are simply ignored by it.
"""

from typing import Dict, List, NamedTuple

from mc_server_maker.i18n import language


class PropInfo(NamedTuple):
    key: str
    default: str
    en: str
    ko: str

    @property
    def is_bool(self) -> bool:
        return self.default in ("true", "false")

    def description(self) -> str:
        return self.ko if language() == "ko" else self.en


CATALOG: List[PropInfo] = [
    PropInfo("accepts-transfers", "false", "Accept players transferred from other servers", "다른 서버에서 넘어오는(transfer) 플레이어 허용"),
    PropInfo("allow-flight", "false", "Don't kick players who fly (needed by many mods/plugins)", "비행하는 플레이어를 추방하지 않음 (모드/플러그인에 필요)"),
    PropInfo("allow-nether", "true", "Enable the Nether", "네더 차원 사용"),
    PropInfo("broadcast-console-to-ops", "true", "Show console command output to online OPs", "콘솔 명령 결과를 접속한 OP에게 보여줌"),
    PropInfo("broadcast-rcon-to-ops", "true", "Show RCON command output to online OPs", "RCON 명령 결과를 접속한 OP에게 보여줌"),
    PropInfo("bug-report-link", "", "Link shown on the client's report screen", "클라이언트 신고 화면에 보여줄 링크"),
    PropInfo("difficulty", "easy", "peaceful / easy / normal / hard", "peaceful / easy / normal / hard (평화/쉬움/보통/어려움)"),
    PropInfo("enable-command-block", "false", "Allow command blocks", "커맨드 블록 허용"),
    PropInfo("enable-jmx-monitoring", "false", "Expose JMX metrics (advanced)", "JMX 모니터링 노출 (고급)"),
    PropInfo("enable-query", "false", "Enable the GameSpy4 query protocol", "쿼리(GameSpy4) 프로토콜 사용"),
    PropInfo("enable-rcon", "false", "Enable remote console (RCON)", "원격 콘솔(RCON) 사용"),
    PropInfo("enable-status", "true", "Show the server as online in the server list", "서버 목록에 온라인으로 표시"),
    PropInfo("enforce-secure-profile", "true", "Require Mojang-signed chat keys", "Mojang 서명 채팅 키 요구"),
    PropInfo("enforce-whitelist", "false", "Kick non-whitelisted players when the whitelist reloads", "화이트리스트를 다시 불러올 때 명단에 없는 사람 추방"),
    PropInfo("entity-broadcast-range-percentage", "100", "How far entities are sent to players (10-1000%)", "엔티티가 보이는 거리 비율 (10~1000%)"),
    PropInfo("force-gamemode", "false", "Force the default game mode on join", "접속할 때마다 기본 게임 모드로 강제"),
    PropInfo("function-permission-level", "2", "Permission level of data-pack functions (1-4)", "데이터팩 함수 권한 레벨 (1~4)"),
    PropInfo("gamemode", "survival", "survival / creative / adventure / spectator", "survival / creative / adventure / spectator"),
    PropInfo("generate-structures", "true", "Generate villages, temples, etc.", "마을·사원 등 구조물 생성"),
    PropInfo("generator-settings", "{}", "Custom world generator settings (JSON)", "사용자 지정 월드 생성 설정 (JSON)"),
    PropInfo("hardcore", "false", "Hardcore: players become spectators on death", "하드코어: 죽으면 관전 모드"),
    PropInfo("hide-online-players", "false", "Hide the player list in the server list", "서버 목록에서 접속자 명단 숨김"),
    PropInfo("initial-disabled-packs", "", "Data packs disabled for new worlds", "새 월드에서 끌 데이터팩"),
    PropInfo("initial-enabled-packs", "vanilla", "Data packs enabled for new worlds", "새 월드에서 켤 데이터팩"),
    PropInfo("level-name", "world", "World folder name", "월드 폴더 이름"),
    PropInfo("level-seed", "", "World seed (empty = random)", "월드 시드 (비우면 무작위)"),
    PropInfo("level-type", "minecraft:normal", "minecraft:normal / flat / large_biomes / amplified", "minecraft:normal / flat / large_biomes / amplified"),
    PropInfo("log-ips", "true", "Write player IPs to the log", "로그에 플레이어 IP 기록"),
    PropInfo("max-chained-neighbor-updates", "1000000", "Limit on chained block updates", "연쇄 블록 업데이트 제한"),
    PropInfo("max-players", "20", "Maximum players online", "최대 접속 인원"),
    PropInfo("max-tick-time", "60000", "Watchdog: stop if one tick takes longer (ms, -1 = off)", "한 틱이 이보다 길면 서버 중지 (ms, -1 = 끔)"),
    PropInfo("max-world-size", "29999984", "World border radius in blocks", "월드 크기 (블록 반경)"),
    PropInfo("motd", "A Minecraft Server", "Description shown in the server list", "서버 목록에 보이는 설명"),
    PropInfo("network-compression-threshold", "256", "Compress packets larger than this (bytes, -1 = off)", "이 크기보다 큰 패킷 압축 (바이트, -1 = 끔)"),
    PropInfo("online-mode", "true", "Check accounts with Mojang (off = non-premium allowed)", "정품 인증 (끄면 비정품 접속 허용)"),
    PropInfo("op-permission-level", "4", "Default OP permission level (1-4)", "OP 기본 권한 레벨 (1~4)"),
    PropInfo("pause-when-empty-seconds", "60", "Pause the world after this many seconds with nobody online (1.21.2+)", "아무도 없으면 이 초 뒤에 월드 일시정지 (1.21.2+)"),
    PropInfo("player-idle-timeout", "0", "Kick idle players after N minutes (0 = never)", "N분 동안 가만히 있으면 추방 (0 = 안 함)"),
    PropInfo("prevent-proxy-connections", "false", "Block players whose IP differs from Mojang's record", "Mojang 기록과 IP가 다른 접속 차단"),
    PropInfo("pvp", "true", "Players can hurt each other", "플레이어끼리 공격 가능"),
    PropInfo("query.port", "25565", "Query protocol port", "쿼리 포트"),
    PropInfo("rate-limit", "0", "Max packets per second per player (0 = no limit)", "플레이어당 초당 최대 패킷 (0 = 제한 없음)"),
    PropInfo("rcon.password", "", "RCON password", "RCON 비밀번호"),
    PropInfo("rcon.port", "25575", "RCON port", "RCON 포트"),
    PropInfo("region-file-compression", "deflate", "World file compression: deflate / lz4 / none", "월드 파일 압축: deflate / lz4 / none"),
    PropInfo("require-resource-pack", "false", "Kick players who decline the resource pack", "리소스팩을 거부하면 추방"),
    PropInfo("resource-pack", "", "Resource pack download URL", "리소스팩 다운로드 주소"),
    PropInfo("resource-pack-id", "", "Resource pack UUID", "리소스팩 UUID"),
    PropInfo("resource-pack-prompt", "", "Message shown when asking for the resource pack", "리소스팩 요청 메시지"),
    PropInfo("resource-pack-sha1", "", "Resource pack SHA-1 checksum", "리소스팩 SHA-1 체크섬"),
    PropInfo("server-ip", "", "Bind to this IP (empty = all)", "이 IP에서만 열기 (비우면 전체)"),
    PropInfo("server-port", "25565", "Server port (TCP)", "서버 포트 (TCP)"),
    PropInfo("simulation-distance", "10", "How far (chunks) the world keeps ticking around players", "플레이어 주변에서 월드가 움직이는 거리 (청크)"),
    PropInfo("spawn-animals", "true", "Spawn animals (older versions)", "동물 스폰 (구버전)"),
    PropInfo("spawn-monsters", "true", "Spawn monsters", "몬스터 스폰"),
    PropInfo("spawn-npcs", "true", "Spawn villagers (older versions)", "주민 스폰 (구버전)"),
    PropInfo("spawn-protection", "16", "Radius around spawn only OPs can build in", "OP만 건축할 수 있는 스폰 주변 반경"),
    PropInfo("sync-chunk-writes", "true", "Write chunks synchronously (safer, slower)", "청크를 즉시 저장 (안전하지만 느림)"),
    PropInfo("text-filtering-config", "", "Chat filter config (advanced)", "채팅 필터 설정 (고급)"),
    PropInfo("text-filtering-version", "0", "Chat filter version (advanced)", "채팅 필터 버전 (고급)"),
    PropInfo("use-native-transport", "true", "Use optimized networking on Linux", "리눅스 네트워크 최적화 사용"),
    PropInfo("view-distance", "10", "How far (chunks) players can see", "플레이어가 볼 수 있는 거리 (청크)"),
    PropInfo("white-list", "false", "Only whitelisted players can join", "화이트리스트에 있는 사람만 접속"),
]

BY_KEY: Dict[str, PropInfo] = {p.key: p for p in CATALOG}
