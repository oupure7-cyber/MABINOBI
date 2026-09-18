# Changelog

## 2026-09-18 (GitHub 공개/공동개발 준비 — 개인정보 제거, Codex 호환성 확보)

- 친구와 Codex(OpenAI)로 공동개발하기 위해 GitHub에 올리기 전 점검 진행
- **개인정보 제거**: `80_GUIDE`(넥슨 공식 페이지 원본 HTML 스크랩)에 로그인 세션 스냅샷(`session.aspx` — `isLogin`/`isMembership`/나이 등)이 그대로 저장돼 있던 것 발견 → 저장소에서 제외(로컬 스크래치패드로 이동, 완전 삭제는 안 함). 유일하게 문서에서 참조하던 작은 아이콘 이미지(`image202609161837011.png`)만 `81_GUIDE_MD/assets/ai_icon.png`로 옮기고 참조 갱신. 분석 내용은 이미 `81_GUIDE_MD` 마크다운 요약에 다 옮겨져 있어 손실 없음
- `.mcp.json`에 개발자 개인 계정 경로(`C:\Users\Ming\...\python.exe`)가 하드코딩돼 있던 것을 `"python"`(PATH 기준)으로 일반화 — 타 유저 배포 시 깨지던 기존 이슈와 동일 원인, 마법사의 "이 PC용으로 자동 설정" 버튼으로 여전히 필요 시 실제 경로로 재작성 가능
- `.gitignore` 신설: `__pycache__/`, `*.pyc`, `.claude/settings.local.json`(로컬 전용 설정), PyInstaller 빌드 산출물 등
- **Codex 호환성 확인**: `.mcp.json`은 Claude Code 전용 포맷이라 Codex CLI가 인식하지 못함(Codex는 `~/.codex/config.toml`에 전역 등록 필요) — `40_ONBOARDING/01_사용자_설치_가이드.md`에 "7단계: Codex 사용자용 설정" 절 추가. `30_MCP_SERVER/server.py` 자체는 표준 MCP(stdio) 서버라 클라이언트 무관하게 동작 확인, `50_APP` 데스크톱 앱도 Claude Code/Codex와 무관하게 CLI 직접 호출이라 영향 없음
- 로컬에 Git 미설치 상태였어서 `winget install Git.Git`으로 설치(2.55.0)

## 2026-09-18 ("강철괴 무한" 자동 루틴 추가 — 라이브 검증은 게임 점검으로 내일로 연기)

- 실제 게임 데이터로 레시피 확인: `get_alterable_items "괴"` → 철괴(광석)/철괴(철 광석) 둘 다 `ProducedPerWork:3`, 강철괴는 철괴 3개 필요(`ProducedPerWork:3`); `get_gatherable_items`로 "광석"/"철 광석"/"석탄" 정확한 `DisplayName` 확인; `get_altering_works`로 시설명이 "금속 가공 시설"이고 이미 강철괴 7개(대기열 풀 상태)가 완료 대기 중인 것 확인
- `steel_routine.py` 신설 (`SteelRoutineWorker`, QThread): `get_altering_works` → 완료분 있으면 `complete_altering_work`로 회수 → 남은 슬롯(7칸 기준) 있으면 보유 재료로 우선순위 결정해 `execute_altering`(철괴 충분하면 강철괴, 아니면 철괴(철광석)/철괴(광석)) 또는 부족한 원자재를 `execute_gathering`으로 채집 → 다음 틱. 실제 행동(회수/등록/채집)이 있었던 틱은 바로 다음 틱으로, 아무것도 못한 틱만 8초 쉬었다가 재시도
  - 안전장치: 응답에 `kind`가 실려오는 `blocked` 상태를 만나면 자동 클릭/우회 없이 즉시 루틴을 멈추고 사용자에게 그대로 안내 (00_SPEC의 "공식 세이프가드 우회 금지" 원칙 그대로 적용) — 1시간 연속 실행 확인 팝업 등도 이 경로로 걸림
  - **알려진 한계**: 정령의 날개 일일 소모 상한 설정 기능은 아직 없음(00_SPEC/03_requirements.md가 요구하는 항목이지만 이번 범위에서 미구현) — 사용자가 직접 정지 버튼으로 멈춰야 함
- `gather_panel.py`에 "🔁 강철괴 무한 시작"/"⏹ 정지" 토글 버튼 추가(채집 버튼 그리드와 다른 색상으로 구분). 실행 중엔 기존 채집 버튼 25개 전부 비활성화, 반대로 채집 버튼 사용 중엔 루틴 시작 불가 — 두 워커가 동시에 CLI를 호출해 충돌하는 것 방지
- 게임 서버 점검으로 실제 `execute_altering`/`execute_gathering` 라운드트립 라이브 검증은 미완료 — 문법 검사 + 오프스크린 스모크 테스트만 통과. 오프스크린 테스트가 "게임 연결 끊긴 상태"에서 간헐적으로 크래시하는 현상 재확인(코드 문제 아님, 이전에도 동일 패턴 확인됨) — 실제 창 기준으로는 게임 연결 끊긴 상태에서도 정상 동작(안내 팝업 정상 표시) 확인

## 2026-09-18 (음악 패널 하단에 악기 변경 바 추가)

- `music_panel.py`에 `InstrumentBar` 추가 — 음악 패널(좌: 검색+카탈로그, 우: 재생/대기열) 아래에 가로 스크롤 바로 배치. `MusicPanel`의 루트 레이아웃을 `QHBoxLayout`에서 `QVBoxLayout`(플레이어 행 + 악기 바)으로 변경
- `get_instruments`로 보유 악기 전체를 버튼으로 생성(체크 가능 버튼, 현재 장착 악기는 눌린 상태로 표시), 클릭하면 `change_instrument` 호출 후 목록 다시 불러와서 장착 상태 갱신
- `refresh_songs()` 호출 시 `InstrumentBar.refresh()`도 함께 실행되도록 연결 (대시보드 연결 성공 시 자동으로 최신 상태 반영)

## 2026-09-18 (중앙 화면 상/하 분할 — 음악 재생 패널 추가)

- 중앙 영역을 `QSplitter(Qt.Vertical)`로 상/하 분할: 상단은 기존 `GatherPanel`(채집 바로가기), 하단은 신설한 `music_panel.py`(`MusicPanel`)
- `MusicPanel` 구성 — 스포티파이류 플레이어 UX:
  - 좌측: 검색창(`QLineEdit`) + 보유 악보 전체 목록(`SongCatalogList`, `get_music_scores` 기반). 검색어 입력 시 즉시 필터링(대소문자 무관 부분일치), 더블클릭으로 대기열 끝에 바로 추가
  - 우측: 현재 재생 중인 곡 표시 + "▶ 대기열 재생"/"⏹ 정지" 버튼 + 재생 대기열(`QueueListWidget`) + 대기열 오른쪽 휴지통(`TrashZone`)
  - 대기열은 내부 드래그로 순서 변경 가능(`QAbstractItemView.DragDrop`), 좌측 카탈로그에서 드래그해 원하는 위치에 끼워넣기 가능(Qt 표준 리스트 간 드래그앤드롭 — 커스텀 MIME 타입 없이 동작), 더블클릭으로 즉시 재생
  - 삭제: 대기열 항목을 드래그해서 우측 휴지통에 놓으면 삭제. `QueueListWidget`이 드래그 시작 시점의 실제 아이템 객체를 기억해뒀다가(`take_dragged_item`) 휴지통이 정확히 그 항목만 제거 — 동일한 제목이 대기열에 여러 개 있어도 엉뚱한 걸 안 지움
  - 재생 종료 감지: 게임에 콜백/이벤트가 없어서 `get_activity`의 `Performance.IsPlaying`을 4초 간격으로 폴링, `False`로 바뀌면 곡이 끝난 것으로 보고 대기열 다음 곡을 자동 재생(진짜 "대기열"처럼 동작하게 하는 핵심 로직)
- `gather_panel.py`에 있던 성공/실패 판정 로직(`_classify`)을 `widgets.classify_cli_result()`로 공용화해서 `music_panel.py`와 함께 재사용 (중복 제거)

## 2026-09-18 (대화 콘솔 제거 → 채집 바로가기 버튼 25개로 교체)

- 화면 중앙의 대화 로그/입력창(`chat_console.py`, `ChatPanel`) 전체 삭제 — 자유 텍스트 파싱(조회 명령어 직접 실행, "OO 채집해줘" 정규식, 그 외 채팅 전송) 기능 전부 제거
- 대신 `gather_panel.py`(`GatherPanel`) 신설: 채집 재료 25개(사용자 지정, 중복 "황금 거미줄" 정리, 가나다순 정렬) 버튼을 4열 그리드로 배치. 클릭 자체가 확인이라 별도 다이얼로그 없이 바로 `get_gatherable_items` 조회 → `execute_gathering` 실행
- 기존 대화 콘솔에서 쓰던 `CliCallWorker`(QThread 비동기 실행, 15분 타임아웃)와 `_classify`(성공/실패 판정) 로직은 `gather_panel.py`로 그대로 이전 — 결과는 로그 대신 패널 하단 상태 라벨 한 줄로 표시(✅/❌ + 사유, `blocked`인 경우 `kind` 안내)

## 2026-09-18 (더블클릭 실행 exe 추가)

- `pip install pyinstaller`
- `launcher/launch_mabinobi.py` 작성 — PySide6/프로젝트 모듈에 의존하지 않는 독립 스크립트. 프로즌 상태에서 `sys.executable`로 exe 자신의 위치를 구해 `AI_Mabinogi` 루트를 찾고, PATH에서 WindowsApps 스토어 스텁을 걸러낸 진짜 `python.exe`를 찾아 `50_APP/main.py`를 `subprocess.Popen`으로 띄우기만 함(앱 코드를 번들링하지 않아 50_APP이 바뀌어도 재빌드 불필요)
- `python -m PyInstaller --onefile --noconsole --name "마비노비"`로 빌드 → 루트에 `마비노비.exe` 생성(7.4MB)
- 실행 검증: exe 더블클릭 → `python.exe 50_APP/main.py` 프로세스 기동 확인 → `EnumWindows`로 실제 "마비노비" 창 제목 확인 완료

## 2026-09-18 (채집 기능 추가 — 실사용 검증 + 타임아웃 버그 발견/수정)

- 대화 콘솔에 채집 요청 파싱 추가: `"<아이템명> [N개|N회|N번] 채집해줘"` 형태를 정규식으로 인식(`parse_gather_request`) → `get_gatherable_items`로 정확한 `DisplayName`/`ToolOk` 조회 → 확인 다이얼로그(정령의 날개 5개 소모, 도구 부족 경고 포함) → `execute_gathering` 실행
- **실사용 테스트**: "황금 개암 버섯 100회 채집해줘" 요청으로 실제 `get_gatherable_items` → `execute_gathering` 라운드트립을 스크립트로 재현해 라이브 실행. 이 과정에서 버그 발견: `execute_gathering`이 기본 180초 타임아웃을 넘겨 우리 쪽 CLI 래퍼(`run_cli`)가 `timeout` 에러로 끊었지만, 게임 쪽 채집 자체는 계속 진행 중이었음(`get_activity`의 `LastRunningInteractionType: Gathering`, `MainButtonState: Stop`으로 확인) — CLI 프로세스만 죽고 게임 액션은 안 끊기는 구조
- 수정: `GATHER_TIMEOUT = 900`(15분)로 늘리고, `execute_gathering` 호출을 `CliCallWorker`(QThread)로 GUI 스레드 밖에서 실행하도록 변경 — 안 그러면 채집 끝날 때까지 앱 전체가 응답 없음(Not Responding) 상태가 됨
- 화면에 "바로가기" 버튼 행 추가, 첫 항목으로 "황금 개암 버섯 채집" 버튼 — 클릭 자체가 확인이므로 별도 확인 다이얼로그 없이 바로 실행(`ChatPanel.QUICK_GATHER_ITEMS`로 항목 추가 가능)
- 중복 로직(아이템 조회) `_lookup_gatherable()`로 공용화, 채집 진행 중 입력창/바로가기 버튼 비활성화(`_set_busy`)로 중복 실행 방지

## 2026-09-18 (앱 이름 확정: 마비노비)

- 앱 이름을 **마비노비(MabiNobi)**로 확정 — "마비노기"+"노비"(옛 신분, 시키는 대로 잔심부름을 대신 해주는 존재) 말장난. `main.py`(`applicationName`), `main_window.py`(창 제목), `onboarding/wizard.py`(환영 페이지), `app_settings.py`(`QSettings` 앱 식별자 `MabiNobi`), 루트/앱 `README.md`에 반영

## 2026-09-18 (창 임베드 기능 제거 — 안티치트로 확인, 대화형 채팅 콘솔로 교체)

- 사용자 확인: "역시 안티치트 때문에 안되나봐" — 자동 감지든 드래그앤드롭이든 결국 같은 `SetParent` 메커니즘이라 근본 원인(안티치트)은 해결 안 됨. `game_embed.py` 전체 삭제, `main_window.py`/`README.md`에서 관련 참조 제거
- 화면 중앙에 `chat_console.py`(`ChatPanel`) 신설 — 이 Claude 세션과 비슷한 형식의 대화 로그(`ChatLog`, 나/AI 턴 구분 + 성공/실패 색상 표시) + 하단 입력창(`ChatInputBar`)
  - 조회형 명령어 19개(`DIRECT_COMMANDS`: capabilities + 조회형 18개)를 그대로 입력하면 `MabinogiMobile_CLI.exe`를 즉시 호출해서 결과를 로그에 표시(마비노기 모바일 MCP가 감싸는 것과 동일한 CLI를 이 앱이 직접 호출하는 구조 그대로 재사용)
  - 그 외 입력은 게임 채팅(`write_chat`)으로 간주하되, 공식 `requiresConfirm` 안전장치를 그대로 앱에도 반영해 **항상 확인 다이얼로그를 거친 뒤에만 전송**
  - `execute_*` 계열(정령의 날개 소모, 구조화된 body 필요)은 이번 범위에서 제외 — 단순 텍스트 입력으로 안전하게 처리하기 어려워 의도적으로 미지원
- 오프스크린 스모크 테스트 중 크래시가 있었으나 원인은 코드가 아니라 테스트 시점에 게임이 꺼져있었던 것으로 확인(사용자가 게임 재실행 후 재검증 요청 → 게임 재연결 후 정상 통과)

## 2026-09-18 (창 임베드 — 드래그앤드롭 수동 선택 추가)

- 자동 감지("게임 창 자동 연결") 결과가 사용자 환경에서 제대로 안 붙는 것 같다는 피드백 → `game_embed.py`에 실행 중인 모든 최상위 창 목록(`list_top_level_windows`, `EnumWindows` 전체 스캔 + `WS_EX_TOOLWINDOW`/오너 창 제외 + 프로세스 이름 조회)을 보여주는 `RunningWindowList`(드래그 소스) 추가
- `GameWindowPanel`에 점선 테두리 드롭존 추가, 목록에서 원하는 창을 직접 드래그해서 놓으면 `_attach_hwnd(hwnd)`로 임베드 — 자동 감지가 엉뚱한 창을 집었을 가능성에 대비해 사용자가 정확한 창을 직접 고를 수 있게 함
- 단, 드래그앤드롭은 트리거 방식만 다를 뿐 내부적으로 동일한 `SetParent` 메커니즘을 쓰므로, 만약 원인이 렌더링/포커스 쪽 문제라면 이것만으로 해결 안 될 수 있음 — 실제 확인 필요

## 2026-09-18 (게임 창 재부모화(임베드) 기능 추가 — 실험적, 안티치트 위험 있음)

- 사용자 요청으로 `50_APP/app/dashboard/game_embed.py` 신설: Win32 `SetParent`(ctypes)로 실행 중인 `MabinogiMobile.exe` 창을 앱 안에 재부모화해서 임베드. **공식 AI 커넥터와 무관한 별도 기법이며, 안티치트(BlackCipher)에 걸릴 위험이 있다고 사용자에게 사전 안내 후 진행** — 패널 안내문에도 동일 경고 표시
  - `tasklist`로 PID 조회(안티치트가 `Get-Process`/.NET API에서 프로세스를 숨기므로) → `EnumWindows`+`GetWindowThreadProcessId`로 메인 창 핸들 탐색 → `QWindow.fromWinId()` + `QWidget.createWindowContainer()`로 임베드
  - 안전장치: 임베드 전 원본 `GWL_STYLE`/`GWL_EXSTYLE` 저장, `detach()`가 `SetParent(hwnd, NULL)` + 스타일 복원 + `SWP_FRAMECHANGED`로 원상 복구. `DashboardWindow.closeEvent`에서 항상 먼저 `detach()` 호출 — 앱 종료 시 게임 창이 자식 창인 채로 같이 파괴되는 사고 방지
  - 실사용 라운드트립 테스트(3초 부착 후 분리) 통과: 분리 후 `GetParent=NULL`, `IsWindow=True`, `IsWindowVisible=True` 확인, `MabinogiMobile_CLI.exe status` 파이프 연결 정상 유지 확인
- 하단 인벤토리/퀘스트·미션/주변 정보 3분할 패널(`SimpleJsonTab`) 전부 제거, 화면 중앙을 게임 창 임베드 패널(`GameWindowPanel`, "게임 창 연결"/"게임 창 연결 해제" 버튼)로 교체 — `widgets.py`의 `JsonView`/`RefreshableTab`도 더 이상 쓰는 곳이 없어 함께 제거

## 2026-09-18 ("내 정보" 패널 제거, 상단 좌측 4x3 스탯으로 대체)

- 하단 4분할의 "내 정보" 칸(`MyInfoTab`) 제거 — 하단은 인벤토리/퀘스트·미션/주변 정보 3분할로 축소
- 대신 상단 컨트롤 바 왼쪽에 `TopStatsPanel` 추가: 전투력/생활력/매력/마도저항, 공격력/최대체력/방어력/데코점수, 힘/솜씨/지력/행운 12개를 4열 x 3행 고정 그리드로 표시 (사용자가 지정한 레이아웃)
- `get_my_info`의 모든 `{DisplayName, Value}` 필드를 범용으로 훑던 `widgets.display_value_entries()`는 더 이상 쓰는 곳이 없어 제거 — 이제 `TOP_STATS_LAYOUT`으로 원하는 필드(API 키 기준)만 고정 매핑

- `widgets.py`에 재화 표시 규칙 추가 (사용자 지정):
  - `HIDDEN_CURRENCY_NAMES`: "원정의 증거: 글라스기브넨 레이드"/"타바르타스 레이드", "심연의 화석"/"붉은 심연의 화석"/"심연의 마석"/"변이된 심연의 화석", "웨카" — entry 자체를 표시하지 않음
  - `TRUNCATED_PREFIXES`: "패키지 포인트"로 시작하는 이름은 뒤에 붙는 이벤트명(예: ": 그랜드 앙상블")을 잘라내고 "패키지 포인트"만 표시 — 이벤트마다 접미사가 바뀔 수 있어서. 아이콘 조회와 툴팁은 잘리지 않은 원본 이름을 그대로 사용(아이콘 매니페스트 키가 원본 이름 기준이라 표시만 축약)

## 2026-09-18 (재화 표시 방식 변경 — 상단 flow → 좌측 단일 컬럼)

- 상단 재화 바(`CurrencyBar` + `FlowLayout`)가 기대만큼 안 나와서 제거. 대신 창 왼쪽에 고정폭(260px) 세로 스크롤 컬럼(`CurrencyColumn`)으로 재화 28개를 아이콘+이름+수량 한 줄씩 쭉 나열
- `FlowLayout` 클래스는 더 이상 쓰는 곳이 없어 제거 (죽은 코드 정리)
- 레이아웃 구조: 컨트롤 바 아래를 `content_row`(좌: 재화 컬럼 / 우: 내정보·인벤토리·퀘스트미션·주변정보 4분할)로 재구성

## 2026-09-18 (CLI 명령어 전체 레퍼런스 작성 + 앱 내 가이드 뷰어)

- 기능 추가 전 분석 단계로, `capabilities` 응답([10_RESEARCH/02_cli_capabilities_raw.json](10_RESEARCH/02_cli_capabilities_raw.json))의 28개 명령 전체를 표로 정리 → [10_RESEARCH/03_cli_command_reference_2026-09-17.md](10_RESEARCH/03_cli_command_reference_2026-09-17.md)
  - 전체 요약표(분류/설명/정령의 날개 소모/사용자 확인) + 조회형 18개 명령의 반환 필드 전체 + 실행형 9개 명령의 입력/성공/실패 코드
  - 공통 패턴 정리: 정령의 날개 소모 3형제, `blocked`+`kind` 안전장치, DisplayName 체이닝 구조, 본인 캐릭터 실명 비노출, 자동성장 명령 부재
  - 파일명에 날짜(2026-09-17, 넥슨 공식 가이드 기준일과 동일) 포함 — 게임 패치로 `capabilities`가 바뀌면 기존 파일은 남겨두고 새 날짜로 별도 파일 추가하는 방식으로 버전 비교
- 대시보드에 "사용 가이드" 버튼 추가 (`app/dashboard/guide_viewer.py`) — `10_RESEARCH/03_cli_command_reference_*.md` 중 파일명 날짜가 가장 최신인 것을 찾아 `QTextBrowser.setMarkdown()`으로 큰 팝업에 렌더링 (표 포함)

## 2026-09-18 (앱 UI 3차 개편 — 레이아웃 피드백 반영)

- 재화 바: `QScrollArea` 가로 스크롤 제거 → Qt 공식 "Flow Layout" 레시피(`widgets.py`의 `FlowLayout`)로 창 너비에 맞춰 자동 줄바꿈. 각 칩에 아이콘 아래 재화 이름도 표시(기존엔 툴팁으로만 노출)
- "내 정보"를 왼쪽 슬라이드 드로어(`InfoDrawer`)에서 하단 4분할의 한 칸(`MyInfoTab`)으로 이동 — 인벤토리/퀘스트·미션/주변 정보와 동일하게 배치, 3컬럼 그리드로 스탯 표시(정렬 순서는 추후 조정 예정)
- `get_my_info`의 `{DisplayName, Value}` 재귀 추출 로직을 `widgets.display_value_entries()`로 공용화 (기존 `InfoDrawer` 전용 코드였던 것을 재사용 가능하게 분리)
- `InfoDrawer` 클래스 및 관련 확장 버튼/애니메이션 코드 제거 (더 이상 안 쓰는 코드 정리)

## 2026-09-18 (앱 UI 2차 개편 — 직관성 개선)

- 상단 메뉴바 제거, 설치 마법사 자동 표시 제거 — 앱 실행 시 바로 대시보드로 진입
- 앱 시작 시 `MabinogiMobile_CLI.exe status`로 게임 연결을 백그라운드 스레드(`app/dashboard/connection.py`)에서 자동 시도. 실패 시 `app/dashboard/connector_guide.py`의 비모달 안내 팝업(게임 실행 + AI 커넥터 활성화 안내, `AI_CONNECTOR_ON_1/2.png` 첨부) 표시
- 오른쪽 상단에 커스텀 슬라이드 토글(`ToggleSwitch`, 직접 페인팅)로 재연결 시도, 성공 시 오른쪽 하단 토스트(`Toast`, 2초 자동 소멸) 표시. 토글 옆에 "설치 마법사" 버튼 추가 (필요 시에만 수동으로 열기)
- 사용자가 제공한 게임 내 재화 화면 스크린샷 2장(`MabinogiMobile_2026091803184283.png`, `MabinogiMobile_2026091803191017.png`)에서 재화 아이콘 28개를 픽셀 좌표 기반으로 전부 자동 크롭 → `50_APP/app/dashboard/assets/currency_icons/`, `get_currencies` API의 `DisplayName`과 1:1 매핑되는 `manifest.json` 생성. 화면 상단 `CurrencyBar`에 아이콘+수량 칩으로 표시
- "내 정보"를 왼쪽에서 슬라이드로 펼쳐지는 `InfoDrawer`로 변경 — `get_my_info` 응답을 재귀 순회해 `{DisplayName, Value}` 형태 항목만 표시, `Vitals`는 제외(메인 화면에 별도 표시 예정, 미구현)
- 인벤토리/퀘스트·미션/주변 정보를 탭 대신 화면 하단 3분할 컬럼으로 배치
- `pip install pillow` (아이콘 크롭용, 스크래치패드 스크립트에서만 사용)
- 오프스크린 스모크 테스트(이벤트 루프 포함) 통과, 실제 창 실행으로 확인

## 2026-09-18 (앱 UI 1차 구현)

- 기술 스택 결정: Python + PySide6 (기존 `30_MCP_SERVER`와 언어 통일), 설치 마법사는 별도 앱이 아니라 메인 제어 앱의 첫 화면으로 통합
- `pip install PySide6` (6.11.2)
- `50_APP/` 신설 — PySide6 데스크톱 앱
  - `app/cli_client.py`: `MabinogiMobile_CLI.exe`를 MCP 없이 직접 호출하는 래퍼 (대시보드는 게임 클라이언트 + CLI만 있으면 동작, Claude Code 불필요)
  - `app/onboarding/checks.py`, `app/onboarding/wizard.py`: `40_ONBOARDING` 가이드의 6단계를 `QWizard`로 구현. Node.js/Claude Code/Python/`mcp` 패키지/게임 연결 상태는 실제로 감지, 계정 로그인·구독은 자동 감지 불가능해 안내+링크만 제공. "이 PC용으로 자동 설정" 버튼으로 `.mcp.json`의 Python 경로를 현재 PC 기준으로 재작성 가능 (기존 `.mcp.json`이 Ming 계정 경로로 하드코딩되어 있어 타 유저 배포 시 깨지는 문제를 여기서 해결)
  - `app/dashboard/main_window.py`: 온보딩 이후 화면. 내 정보/재화/인벤토리/퀘스트·미션/주변 정보를 CLI 직접 호출로 조회 (재화는 표, 나머지는 JSON 뷰). 상태바에 게임 연결 상태 30초 주기 폴링
  - 스케줄러/조건 기반 자동 트리거(F1~F4)는 아직 없음 — 현재는 "조회" 기능만 구현됨
- 오프스크린 모드(`QT_QPA_PLATFORM=offscreen`)로 마법사/대시보드 생성 스모크 테스트 통과, 실제 창 실행으로 게임 데이터 정상 조회 확인

## 2026-09-18 (배포 준비)

- 타 유저 배포를 목표로, 지금까지 실제로 거친 설치 과정(Claude Code 설치, Claude 계정 생성/로그인, 구독 연결, MCP 연결용 Python 설치, 프로젝트 MCP 서버 연결, 게임 내 AI 커넥터 활성화)을 정리한 사용자 설치 가이드 작성 → [40_ONBOARDING/01_사용자_설치_가이드.md](40_ONBOARDING/01_사용자_설치_가이드.md)
- `README.md`에 `40_ONBOARDING` 폴더 및 진행 상태 반영

## 2026-09-18

- 넥슨 공식 "마비노기 모바일 AI 커넥터" 안내 페이지 스크랩 및 마크다운 요약 정리 (`80_GUIDE`, `81_GUIDE_MD`)
- 프로젝트 명세 체계 초기 구성: `README.md`, `00_SPEC/01_project_overview.md`, `00_SPEC/02_scope_boundaries.md`, `00_SPEC/03_requirements.md`, `10_RESEARCH/01_ai_connector_interface.md`(빈 템플릿), `20_DESIGN/01_architecture.md`(빈 템플릿) 작성
- `C:\Nexon\MabinogiMobile\MabinogiMobile_CLI.exe`를 실제로 실행해 AI 커넥터 인터페이스 조사: `status`/`capabilities`/`get_current_environment` 호출 성공, 명령 28개 전체 스키마 확보 → [10_RESEARCH/01_ai_connector_interface.md](10_RESEARCH/01_ai_connector_interface.md), 원본 [10_RESEARCH/02_cli_capabilities_raw.json](10_RESEARCH/02_cli_capabilities_raw.json)
- 발견: 안티치트(BlackCipher)로 인해 `MabinogiMobile.exe`가 PowerShell `Get-Process`에는 안 보이고 `tasklist`로만 보임. Claude Code에 MCP 서버가 아직 자동 등록되어 있지 않음(등록 트리거 조건은 추가 조사 필요)
- Python 3.12 설치(winget), `pip install mcp`(v2.2.0 — API가 `FastMCP`에서 `MCPServer`로 개편됨, `mcp.server.mcpserver.MCPServer` 사용)
- `30_MCP_SERVER/server.py` 작성: CLI 28개 명령을 1:1 MCP 툴로 래핑. `get_current_environment`/`get_currencies` 실제 호출로 정상 동작 확인
- 프로젝트 루트 `.mcp.json`에 `mabinogi-ai-connector` 서버 등록, `20_DESIGN/01_architecture.md` 실제 아키텍처로 갱신
