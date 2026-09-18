# 제어 프로그램 아키텍처

## 현재 구성 (2026-09-18)

```
Claude Code (이 프로젝트를 열면 .mcp.json으로 자동 연결)
        │  MCP (stdio)
        ▼
30_MCP_SERVER/server.py  (Python, mcp SDK MCPServer)
        │  subprocess: "MabinogiMobile_CLI.exe <command> [body]"
        ▼
MabinogiMobile_CLI.exe  (Devcat 제공, named pipe로 게임과 통신)
        │
        ▼
MabinogiMobile.exe (실행 중인 게임 클라이언트)
```

- **MCP 서버** (`30_MCP_SERVER/server.py`): [10_RESEARCH/02_cli_capabilities_raw.json](../10_RESEARCH/02_cli_capabilities_raw.json)의 28개 명령을 1:1로 MCP 툴로 노출. 자세한 설계는 [30_MCP_SERVER/README.md](../30_MCP_SERVER/README.md).
- **등록**: 프로젝트 루트 `.mcp.json`. Claude Code가 이 프로젝트 폴더를 열 때 자동으로 서버를 spawn.
- **CLI 클라이언트**: 별도 구현 없이 넥슨이 제공하는 `MabinogiMobile_CLI.exe`를 그대로 서브프로세스로 호출 (research 단계에서 확인한 "1회성 호출 → JSON 응답" 패턴을 그대로 사용).

## 안전장치 연동 지점 (구현 완료)

- `write_chat` 툴 설명에 "게임 내 승인 없이는 전송되지 않음"을 명시 — CLI/게임 자체의 `requiresConfirm` 정책에 의존, 서버가 별도로 승인을 대신하지 않음.
- `execute_gathering`/`execute_crafting`/`execute_altering` 툴 설명에 "정령의 날개 5개 소모"를 명시.
- CLI가 `blocked`(kind 포함)를 반환하면 `_run_cli`는 그 응답을 그대로 통과시킬 뿐 자동으로 재시도/클릭하지 않음 — Claude Code가 이 결과를 사용자에게 그대로 전달해야 함.
- 금지 범위(거래소/캐시샵/길드운영/1:1메시지/외부연동)에 대응하는 명령이 capabilities에 없어, 화이트리스트 필터링 코드 없이도 범위가 지켜짐.

## 다음 단계 (미구현)

[00_SPEC/03_requirements.md](../00_SPEC/03_requirements.md)의 "스케줄러"는 아직 없음 — 지금은 Claude Code 대화 중에 사용자가 요청할 때만 툴이 호출된다 (기존 AI 커넥터의 대화형 사용과 동일, 다만 게임을 직접 켜지 않고 Claude Code 세션에서 바로 호출 가능해짐). 조건/스케줄 기반 자동 트리거(F1~F4)를 만들려면:

- 상시 실행되는 스케줄러 프로세스 필요 여부 결정 (OS 스케줄 작업 vs Python 상시 루프)
- 스케줄러가 MCP 서버를 거치지 않고 `_run_cli`를 직접 호출할지, 아니면 스케줄러 자체를 또 하나의 MCP 클라이언트로 만들지 결정
- 로그 저장 형식/위치 결정
