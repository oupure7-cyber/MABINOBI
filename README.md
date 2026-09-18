# AI_Mabinogi — 마비노비 (MabiNobi)

마비노기 모바일 공식 **AI 커넥터** 기능을 활용해, 허용된 범위 내에서 반복적인 게임 동작(채집/제작/정보조회 등)을 자동으로 요청해주는 제어 프로그램(앱 이름: **마비노비**, "마비노기"+"노비" — 시키는 대로 게임 잔심부름을 대신 해주는 존재라는 말장난)을 만들기 위한 프로젝트.

## 배경

넥슨은 2026년 9월, PC 버전 마비노기 모바일에서 Claude Code / Cursor / Gemini CLI 등 로컬 AI 도구와 게임 클라이언트를 연결해 채팅·채집·제작·가공 등을 대화형으로 요청할 수 있는 **AI 커넥터** 기능을 공식 출시했다. 이 프로젝트는 그 공식 기능을 기반으로, 사용자가 매번 대화로 요청하지 않아도 원하는 동작이 자동으로 수행되도록 하는 제어 프로그램을 만드는 것을 목표로 한다.

공식 기능 요약: [81_GUIDE_MD/마비노기_모바일_AI_커넥터_가이드.md](81_GUIDE_MD/마비노기_모바일_AI_커넥터_가이드.md)

## 폴더 구조

| 경로 | 설명 |
|---|---|
| [README.md](README.md) | 이 문서. 프로젝트 진입점 |
| [00_SPEC](00_SPEC) | 명세 — 무엇을 만들 것인가, 어디까지 허용되는가, 요구사항 |
| [10_RESEARCH](10_RESEARCH) | 조사 — AI 커넥터가 실제로 노출하는 인터페이스(MCP 툴 등) 기록. 전체 28개 명령 필드별 레퍼런스(패치될 때마다 날짜 붙여서 갱신): [03_cli_command_reference_2026-09-17.md](10_RESEARCH/03_cli_command_reference_2026-09-17.md) |
| [20_DESIGN](20_DESIGN) | 설계 — 제어 프로그램 아키텍처 |
| [30_MCP_SERVER](30_MCP_SERVER) | 구현 — AI 커넥터 CLI를 감싸는 MCP 서버 (Python), Claude Code에 연결 |
| [40_ONBOARDING](40_ONBOARDING) | 배포 — 타 유저 대상 설치/연결 가이드 (Claude Code 설치, 계정/구독 연결, Python 설치 등) |
| [50_APP](50_APP) | 구현 — **마비노비**, PySide6 데스크톱 앱. 설치 마법사(40_ONBOARDING을 화면으로 구현, 버튼으로 열림), 대시보드(스탯/재화 조회), 채집 바로가기 25종 + "가공 무한" 자동 루틴(강철괴/목재+/옷감+/가죽+ 4종 동시), 음악 플레이어(대기열/악기 변경) |
| [81_GUIDE_MD](81_GUIDE_MD) | 넥슨 공식 AI 커넥터 안내 페이지를 정리한 마크다운 요약 (원본 HTML 스크랩은 로그인 세션 정보가 섞여있어 저장소에서 제외함) |
| [.mcp.json](.mcp.json) | Claude Code/Codex 등 MCP 클라이언트용 서버 등록 파일 (Claude Code는 자동 인식, Codex는 `~/.codex/config.toml`에 별도 등록 필요 — [40_ONBOARDING](40_ONBOARDING) 참고) |
| [마비노비.exe](마비노비.exe) | **더블클릭 실행 런처.** `launcher/launch_mabinobi.py`를 PyInstaller로 빌드. 시스템 Python을 찾아 `50_APP/main.py`를 실행만 해주는 얇은 실행기(앱 자체를 번들링한 게 아니라서 Python·PySide6가 설치되어 있어야 함) |
| [launcher](launcher) | 위 exe의 소스 (`launch_mabinobi.py`) |
| [CHANGELOG.md](CHANGELOG.md) | 진행 로그 |

## 현재 진행 상태

1. ✅ 공식 가이드 스크랩 및 요약 (`81_GUIDE_MD`)
2. ✅ 명세 문서 체계 구성 (`00_SPEC`, `README.md`, `CHANGELOG.md`)
3. ✅ AI 커넥터 인터페이스 조사 (`10_RESEARCH`) — `MabinogiMobile_CLI.exe` 명령 28개 전체 스키마 확보
4. ✅ 아키텍처 설계 (`20_DESIGN`)
5. ✅ 구현 — `30_MCP_SERVER`로 CLI 28개 명령을 MCP 툴로 래핑, `.mcp.json`으로 Claude Code에 연결 완료
6. ✅ 배포 준비 — 타 유저 대상 설치 가이드 작성 (`40_ONBOARDING`), 더블클릭 실행 런처(`마비노비.exe`)
7. 🟡 앱 UI 구현 — PySide6 대시보드(`50_APP`). 스탯/재화 조회, 채집 바로가기, 음악 재생/악기 변경 + "가공 무한" 조건 기반 자동 루틴(강철괴/목재+/옷감+/가죽+ 4개 체인을 한 루프가 라운드로빈으로 순회, F1 채집 + F3 가공 트리거를 재료 버퍼 규칙으로 일반화)까지 완료. 정령의 날개 하루 소모 상한 설정, 게임 채팅 전송 UI는 아직 없음(다음 단계)

## 지켜야 할 경계선 (요약)

- **허용**: 채팅(사용자 승인 필요)/퀘스트·미션 조회/내정보 조회/채집·낚시/제작·가공/연주/주변 정보 조회
- **금지**: 거래소 등록·구매, 성장과 관련된 자동 플레이, 결제/캐시샵, 길드 운영, 1:1 메시지, 아이템 버리기/분해, 외부 메신저 연동
- 자세한 내용: [00_SPEC/02_scope_boundaries.md](00_SPEC/02_scope_boundaries.md)
