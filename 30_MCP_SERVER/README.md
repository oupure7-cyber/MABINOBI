# mabinogi-ai-connector MCP 서버

[10_RESEARCH/01_ai_connector_interface.md](../10_RESEARCH/01_ai_connector_interface.md)에서 확인한 `MabinogiMobile_CLI.exe`(넥슨 공식 AI 커넥터 CLI)를 감싸서, Claude Code가 표준 MCP 툴로 쓸 수 있게 해주는 로컬 서버.

## 구성

- `server.py` — [mcp](https://pypi.org/project/mcp/) 공식 Python SDK(`MCPServer`, v2.x)로 작성. `capabilities` 응답의 28개 명령을 1:1로 MCP 툴로 노출.
- `_run_cli()` 헬퍼가 매 호출마다 `MabinogiMobile_CLI.exe <command> [body]`를 서브프로세스로 실행하고 JSON stdout을 파싱해서 반환. CLI 경로는 환경변수 `MABINOGI_CLI_PATH`로 바꿀 수 있음 (기본값 `C:\Nexon\MabinogiMobile\MabinogiMobile_CLI.exe`).
- 오류(파일 없음/타임아웃/빈 응답/JSON 파싱 실패)는 예외를 던지지 않고 `{"error": ..., "message": ...}` 형태로 반환 — MCP 툴 결과로 그대로 노출됨.

## 설치

이 프로젝트에서는 Python 3.12(winget `Python.Python.3.12`)를 설치하고 `pip install mcp`로 세팅했다.

```
pip install -r 30_MCP_SERVER/requirements.txt
```

## Claude Code 연결

프로젝트 루트 `.mcp.json`에 등록되어 있어, 이 프로젝트를 Claude Code에서 열면 자동으로 인식된다 (신규 MCP 서버라 최초 1회 승인 프롬프트가 뜬다).

수동으로 단독 실행해서 확인하려면:

```
python 30_MCP_SERVER/server.py
```

(stdio 트랜스포트로 대기 상태가 되며, MCP 클라이언트가 붙기 전까지는 별다른 출력 없이 대기한다 — 정상 동작.)

## 안전 범위

[00_SPEC/02_scope_boundaries.md](../00_SPEC/02_scope_boundaries.md)의 금지 목록(거래소/캐시샵/길드운영/1:1메시지/외부연동/자동성장플레이)에 대응하는 명령이 CLI `capabilities`에 존재하지 않으므로, 이 서버는 별도의 화이트리스트 필터링 없이 캐퍼빌리티를 그대로 노출한다. 게임 업데이트로 새 명령이 추가되면 먼저 `00_SPEC/02_scope_boundaries.md`를 재검토한 뒤 여기에 반영할 것.
