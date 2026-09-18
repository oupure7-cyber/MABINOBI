# 마비노비 (MabiNobi)

넥슨 공식 AI 커넥터 CLI(`MabinogiMobile_CLI.exe`)를 직접 호출하는 PySide6 데스크톱 앱. "마비노기"의 "노비"(옛 신분 — 시키는 대로 게임 잔심부름을 대신 해주는 존재라는 뜻의 말장난). Claude Code/MCP 없이도 동작한다 — MCP는 "Claude에게 대화로 요청" 용도이고, 이 앱은 "화면으로 조회/제어" 용도로 별개다.

## 실행

```
pip install -r 50_APP/requirements.txt
python 50_APP/main.py
```

또는 프로젝트 루트의 [마비노비.exe](../마비노비.exe)를 더블클릭 — `main.py`를 PyInstaller `--onefile`로 직접 빌드한 완전 독립 실행 파일이라(2026-09-19~) Python도, 이 프로젝트 폴더도 필요 없이 exe 하나만 있으면 바로 실행된다. 빌드 명령은 `50_APP/`에서:
```
python -m PyInstaller --onefile --noconsole --name "마비노비" --distpath .. --add-data "app/dashboard/assets;app/dashboard/assets" --add-data "app/dashboard/AI_CONNECTOR_ON_1.png;app/dashboard" --add-data "app/dashboard/AI_CONNECTOR_ON_2.png;app/dashboard" main.py
```

## 구성

- `main.py` — 진입점. 바로 대시보드로 진입 (설치 마법사는 자동으로 뜨지 않음, 버튼으로만 열림).
- `app/cli_client.py` — `MabinogiMobile_CLI.exe` 서브프로세스 호출 래퍼 (`MABINOGI_CLI_PATH` 환경변수로 경로 변경 가능, 기본값은 `30_MCP_SERVER/server.py`와 동일).
- `app/app_settings.py` — `QSettings` 기반 앱 상태(온보딩 완료 여부. 현재는 마법사가 수동 호출로만 열려 직접적인 게이팅 용도로는 안 쓰임).
- `app/onboarding/` — 설치 마법사(`wizard.py`)와 환경 감지 로직(`checks.py`). [40_ONBOARDING/01_사용자_설치_가이드.md](../40_ONBOARDING/01_사용자_설치_가이드.md)의 6단계를 화면으로 구현. 대시보드 우상단 "설치 마법사" 버튼으로 열림.
- `app/dashboard/` — 메인 화면. 레이아웃: 상단 컨트롤 바(스탯 4x3 + MCP 연결 토글/설치 마법사/사용 가이드) → 본문 좌측 재화 컬럼 + 중앙(상: 가공 무한 토글, 하: 음악 플레이어) + 우측 JOB 대기열 컬럼.
  - `main_window.py` — 메뉴바 없음. 앱 실행 시 `connection.py`(백그라운드 스레드)로 게임 연결 자동 시도, 실패 시 `connector_guide.py` 비모달 팝업(게임 내 AI 커넥터 활성화 안내 + 스크린샷 2장). `TopStatsPanel`(전투력/생활력/매력/마도저항/공격력/최대체력/방어력/데코점수/힘/솜씨/지력/행운, 4x3 고정 그리드)이 컨트롤 바 왼쪽에 있음. 중앙은 `QSplitter(Vertical)`로 `GatherPanel`/`MusicPanel` 분할, 오른쪽엔 고정폭 `JobQueuePanel`.
  - `widgets.py` — `ToggleSwitch`, `Toast`, `CurrencyColumn`(왼쪽 세로 스크롤 재화 목록, 일부 항목 숨김/이름 축약 규칙 포함), `classify_cli_result()`(CLI 응답 성공/실패 공용 판정 — 여러 패널이 재사용).
  - `gather_panel.py` — "🔁 가공 무한 시작" 토글 버튼(`altering_routine.py` 실행/정지) + 상태 라벨만 남음. 예전엔 채집 바로가기 버튼 25개도 있었지만 2026-09-18에 JOB 대기열로 이전하면서 제거됨.
  - `altering_routine.py` — "가공 무한" 루틴 본체(`AlteringRoutineWorker`, QThread). 강철괴/목재+/옷감+/가죽+ 4개 가공 체인을 라운드로빈으로 순회하며 시설별로 회수→그리디하게 최대한 채우기, 원자재는 7작업분의 5배를 목표로 선제 채집. `duration_seconds` 옵션으로 유한 시간 후 자동 종료 가능(JOB 대기열의 "가공무한 1시간"이 이걸 사용). `blocked` 응답을 만나면 자동 우회 없이 즉시 정지.
  - `routine_dashboard.py` — "가공 무한" 실행 중 뜨는 독립 창. 재료/생산물 전량과 시설별 대기열(n/7, 완료 개수 강조) 표시. CLI를 직접 호출하지 않고 워커의 `snapshot` 시그널만 구독.
  - `job_queue.py` — 화면 우측 JOB 대기열(`JobQueuePanel`). 유한한 자동화 작업(JOB)을 순서대로 반복 실행(`◀ N ▶` 1~9회), 휴지통으로 삭제(실행 중인 JOB이면 중단 후 다음 진행), `blocked` 시 전체 일시정지+재개. 하단에 검색 가능한 JOB 카탈로그(`JOB_CATALOG`): "가공무한 1시간", "야채볶음10개"/"야채볶음 50개"(`food_crafting_job.py`), "채집: `<이름>` x100" 25종(`gather_job.py`, 예전 채집 바로가기 버튼을 대체).
  - `food_crafting_job.py` — 재료 채집→`execute_crafting` 1회성 JOB 타입(`FoodCraftWorker`). 부족한 재료만 채집 후 목표 개수 제작, 시설의 1회 제작 상한(`invalid_count`+`maxCount`)에 걸리면 자동 분할.
  - `gather_job.py` — 채집 한 번짜리 1회성 JOB 타입(`GatherJobWorker`) + `GATHER_ITEMS`(예전 버튼 목록, 25종).
  - `music_panel.py` — 스포티파이류 플레이어. 좌: 검색창 + 보유 악보 카탈로그(`get_music_scores`, 드래그 소스). 우: 현재 재생 곡 + 재생 대기열(드래그로 순서 변경/카탈로그에서 끼워넣기/휴지통으로 삭제) + 하단 `InstrumentBar`(보유 악기 버튼, 클릭 시 `change_instrument`). 대기열은 게임에 없는 개념이라 `get_activity`의 `Performance.IsPlaying`을 4초 간격 폴링해서 곡이 끝나면 자동으로 다음 곡 재생.
  - `guide_viewer.py` — "사용 가이드" 버튼 → `10_RESEARCH/03_cli_command_reference_*.md` 중 최신 날짜 파일을 `QTextBrowser.setMarkdown()`으로 큰 팝업에 렌더링.
  - `assets/currency_icons/` — 게임 내 재화 화면 스크린샷에서 크롭한 아이콘 28개 + `manifest.json`(`get_currencies`의 `DisplayName` 매핑).

## 알아둘 것

- `.mcp.json`의 Python 경로는 설치 PC마다 다르다. 설치 마법사 5단계의 "이 PC용으로 자동 설정" 버튼이 현재 PC에서 감지된 Python 경로로 `.mcp.json`을 재작성해준다 (Claude Code로 대화형 사용을 하려는 유저 대상).
- 정령의 날개를 소모하는 실행형 명령(`execute_gathering`, `execute_altering`, `execute_crafting`)은 **가공 무한 루틴**과 **JOB 대기열**(채집/제작 JOB들)로 실제로 호출된다. 추가/변경 시 [00_SPEC/02_scope_boundaries.md](../00_SPEC/02_scope_boundaries.md)와 공식 세이프가드(사용자 승인, `blocked` 자동 우회 금지)를 그대로 지켜야 한다.
- **알려진 한계**: [00_SPEC/03_requirements.md](../00_SPEC/03_requirements.md)가 요구하는 "정령의 날개 하루 소모 상한 설정" 기능이 아직 없다 — 가공 무한 루틴/JOB 대기열 모두 사용자가 직접 정지해야 멈춘다(가공 무한 JOB은 시간제한으로 자동 종료됨).
- 대화형 자유 텍스트 콘솔(`chat_console.py`)은 만들었다가 **제거했다** — 채집/조회 모두 각 패널·JOB이 직접 담당하는 방식으로 대체.
- 게임 창을 앱 안에 재부모화(임베드)하는 기능도 시도했다가 **제거했다** — 안티치트(BlackCipher)에 의해 제대로 동작하지 않는 것으로 판단됨.
- (위 두 가지 다 `git`이 없는 프로젝트라 이전 코드가 필요하면 이 대화 기록에서 복원해야 한다. 자세한 경위는 [CHANGELOG.md](../CHANGELOG.md) 참고.)
