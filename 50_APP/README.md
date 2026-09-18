# 마비노비 (MabiNobi)

넥슨 공식 AI 커넥터 CLI(`MabinogiMobile_CLI.exe`)를 직접 호출하는 PySide6 데스크톱 앱. "마비노기"의 "노비"(옛 신분 — 시키는 대로 게임 잔심부름을 대신 해주는 존재라는 뜻의 말장난). Claude Code/MCP 없이도 동작한다 — MCP는 "Claude에게 대화로 요청" 용도이고, 이 앱은 "화면으로 조회/제어" 용도로 별개다.

## 실행

```
pip install -r 50_APP/requirements.txt
python 50_APP/main.py
```

또는 프로젝트 루트의 [마비노비.exe](../마비노비.exe)를 더블클릭 (`launcher/launch_mabinobi.py`를 PyInstaller로 빌드한 얇은 런처 — 시스템 Python을 찾아 위 명령을 대신 실행해줄 뿐, 앱 자체를 번들링한 건 아니라서 Python/의존성은 그대로 설치돼 있어야 함).

## 구성

- `main.py` — 진입점. 바로 대시보드로 진입 (설치 마법사는 자동으로 뜨지 않음, 버튼으로만 열림).
- `app/cli_client.py` — `MabinogiMobile_CLI.exe` 서브프로세스 호출 래퍼 (`MABINOGI_CLI_PATH` 환경변수로 경로 변경 가능, 기본값은 `30_MCP_SERVER/server.py`와 동일).
- `app/app_settings.py` — `QSettings` 기반 앱 상태(온보딩 완료 여부. 현재는 마법사가 수동 호출로만 열려 직접적인 게이팅 용도로는 안 쓰임).
- `app/onboarding/` — 설치 마법사(`wizard.py`)와 환경 감지 로직(`checks.py`). [40_ONBOARDING/01_사용자_설치_가이드.md](../40_ONBOARDING/01_사용자_설치_가이드.md)의 6단계를 화면으로 구현. 대시보드 우상단 "설치 마법사" 버튼으로 열림.
- `app/dashboard/` — 메인 화면. 레이아웃: 상단 컨트롤 바(스탯 4x3 + MCP 연결 토글/설치 마법사/사용 가이드) → 본문 좌측 재화 컬럼 + 중앙(상: 채집 바로가기, 하: 음악 플레이어).
  - `main_window.py` — 메뉴바 없음. 앱 실행 시 `connection.py`(백그라운드 스레드)로 게임 연결 자동 시도, 실패 시 `connector_guide.py` 비모달 팝업(게임 내 AI 커넥터 활성화 안내 + 스크린샷 2장). `TopStatsPanel`(전투력/생활력/매력/마도저항/공격력/최대체력/방어력/데코점수/힘/솜씨/지력/행운, 4x3 고정 그리드)이 컨트롤 바 왼쪽에 있음. 중앙은 `QSplitter(Vertical)`로 `GatherPanel`/`MusicPanel` 분할.
  - `widgets.py` — `ToggleSwitch`, `Toast`, `CurrencyColumn`(왼쪽 세로 스크롤 재화 목록, 일부 항목 숨김/이름 축약 규칙 포함), `classify_cli_result()`(CLI 응답 성공/실패 공용 판정 — 여러 패널이 재사용).
  - `gather_panel.py` — 채집 바로가기 25개 버튼(가나다순, 클릭이 곧 확인이라 별도 팝업 없음) + "🔁 강철괴 무한 시작" 토글 버튼(`steel_routine.py` 실행/정지). `CliCallWorker`(QThread)로 `execute_gathering`을 GUI 스레드 밖에서 실행(최대 15분 타임아웃 — 100개 채집이 오래 걸릴 수 있어서).
  - `steel_routine.py` — "강철괴 무한" 루틴 본체(`SteelRoutineWorker`, QThread). `get_altering_works`로 금속 가공 시설(7슬롯) 상태 확인 → 완료분 `complete_altering_work` 회수 → 빈 슬롯 있으면 보유 재료로 강철괴/철괴 중 우선순위 판단해 `execute_altering`, 부족하면 `execute_gathering`으로 원자재(광석/철 광석/석탄) 보충 → 반복. `blocked` 응답(1시간 연속 실행 확인 팝업 등)을 만나면 자동 우회 없이 즉시 정지. **정령의 날개 일일 소모 상한은 아직 없음** — 사용자가 직접 정지해야 함.
  - `music_panel.py` — 스포티파이류 플레이어. 좌: 검색창 + 보유 악보 카탈로그(`get_music_scores`, 드래그 소스). 우: 현재 재생 곡 + 재생 대기열(드래그로 순서 변경/카탈로그에서 끼워넣기/휴지통으로 삭제) + 하단 `InstrumentBar`(보유 악기 버튼, 클릭 시 `change_instrument`). 대기열은 게임에 없는 개념이라 `get_activity`의 `Performance.IsPlaying`을 4초 간격 폴링해서 곡이 끝나면 자동으로 다음 곡 재생.
  - `guide_viewer.py` — "사용 가이드" 버튼 → `10_RESEARCH/03_cli_command_reference_*.md` 중 최신 날짜 파일을 `QTextBrowser.setMarkdown()`으로 큰 팝업에 렌더링.
  - `assets/currency_icons/` — 게임 내 재화 화면 스크린샷에서 크롭한 아이콘 28개 + `manifest.json`(`get_currencies`의 `DisplayName` 매핑).

## 알아둘 것

- `.mcp.json`의 Python 경로는 설치 PC마다 다르다. 설치 마법사 5단계의 "이 PC용으로 자동 설정" 버튼이 현재 PC에서 감지된 Python 경로로 `.mcp.json`을 재작성해준다 (Claude Code로 대화형 사용을 하려는 유저 대상).
- 정령의 날개를 소모하는 실행형 명령(`execute_gathering`, `execute_altering`)은 이제 **채집 바로가기 버튼**과 **강철괴 무한 루틴**으로 실제로 호출된다. 추가/변경 시 [00_SPEC/02_scope_boundaries.md](../00_SPEC/02_scope_boundaries.md)와 공식 세이프가드(사용자 승인, `blocked` 자동 우회 금지)를 그대로 지켜야 한다.
- **알려진 한계**: [00_SPEC/03_requirements.md](../00_SPEC/03_requirements.md)가 요구하는 "정령의 날개 하루 소모 상한 설정" 기능이 아직 없다 — 강철괴 무한 루틴은 사용자가 직접 정지 버튼을 눌러야 멈춘다.
- 대화형 자유 텍스트 콘솔(`chat_console.py`)은 만들었다가 **제거했다** — 대신 채집은 버튼(`gather_panel.py`), 조회는 각 패널이 직접 담당하는 방식으로 대체.
- 게임 창을 앱 안에 재부모화(임베드)하는 기능도 시도했다가 **제거했다** — 안티치트(BlackCipher)에 의해 제대로 동작하지 않는 것으로 판단됨.
- (위 두 가지 다 `git`이 없는 프로젝트라 이전 코드가 필요하면 이 대화 기록에서 복원해야 한다. 자세한 경위는 [CHANGELOG.md](../CHANGELOG.md) 참고.)
