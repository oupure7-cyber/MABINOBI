# 마비노비 (MabiNobi)

넥슨 공식 AI 커넥터 CLI(`MabinogiMobile_CLI.exe`)를 직접 호출하는 PySide6 데스크톱 앱. "마비노기"의 "노비"(옛 신분 — 시키는 대로 게임 잔심부름을 대신 해주는 존재라는 뜻의 말장난). 2026-09-19부로 Claude Code/MCP 채팅 연동 기능은 지원하지 않음(나중에 다시 붙일 수도 있음, [CHANGELOG.md](../CHANGELOG.md) 참고) — 이 앱은 순수하게 "화면으로 조회/제어"만 한다.

## 통합 작업 UI (2026-09-19)

현재 진입 화면은 `app/dashboard/modern_window.py`입니다. 아래의 이전 레이아웃 설명보다 이 절이 우선합니다.

- 상위 메뉴: 작업 / 악보 / 창고. 작업에는 채집 / 요리 / 제작 / 무한가공소가 있습니다.
- 왼쪽에서 작업을 추가하고 오른쪽 통합 대기열에서 시작, 횟수 변경, 순서 이동, 삭제를 합니다. 작업 추가만으로 실행되지 않습니다.
- 전체 일시정지는 이미 요청한 채집·요리 작업이 끝난 후 적용됩니다. 실행 중인 작업은 직접 수정할 수 없으며, 건너뛰기 역시 현재 요청 종료 후 적용됩니다.
- 무한가공소는 기존 가공 워커를 사용하며, 무한 실행과 기존 1시간 실행을 제공합니다. 직접 건너뛰어야 무한 작업 뒤의 작업이 실행됩니다. 가공 현황은 해당 탭 안에서 표시됩니다.
- 요리는 야채볶음과 추가 요리 9종(각 10개/50개), 제작은 장비 12종(각 2개)을 제공합니다. 새 작업은 게임 레시피를 조회하며 부족한 채집·제작 재료를 준비합니다. 별도 가공·구매 재료나 해금 조건이 부족하면 멈춥니다. 목표 수량은 시설이 허용하는 한 한 번의 `execute_crafting` 호출에 몰아서 요청합니다(2026-09-20~ — `execute_crafting`은 `craftCount`와 무관하게 호출마다 정령의 날개를 소모하므로, 여러 번 나눠 부르면 그만큼 낭비). 게임이 꺼져 있어 새 요리·장비의 실제 게임 제작은 아직 검증하지 못했습니다.
- **제작 탭 전용 버튼**(2026-09-20): 검색창 위에 "보유 스크롤 모두 진행"(인벤토리의 "제작 스크롤: `<이름>`"을 전부 확인해서 아는 레시피면 그 보유 개수만큼 반복(◀N▶, 최대 9)으로 대기열에 추가 — 스크롤은 창고 보관이 안 되는 아이템이라 인벤토리만 확인, 모르는 스크롤(아직 JOB으로 안 만든 다른 제작 종류)은 조용히 건너뜀) / 마을별 "주간 제작(마을명)" 4개 / "주간 제작(마을명) x5" 4개. 임무 게시판은 같은 스크롤을 한 주에 최대 3개까지 팔아서(스크롤 1개=장비 2개 목표), "주간 제작"은 그 마을 장비 3종을 각각 x6(3스크롤×2)의 숨은 JOB(`job_queue.py`의 `EQUIPMENT_WEEKLY_X6`)으로 대기열에 추가한다. "x5" 버튼은 목표 15개를 새 x15 JOB을 만드는 대신 기존 `EQUIPMENT_WEEKLY_X10`(5스크롤 배치)과 새 `EQUIPMENT_WEEKLY_X5`를 같이 큐에 넣어 채운다(10+5=15) — 어느 쪽이든 `execute_crafting`을 x2 JOB을 여러 번 반복하는 것보다 적은 호출로 끝냄. 스크롤/카탈로그 이름 매칭은 공백 차이에 안전(`modern_window.py`의 `_find_equipment_spec` — 실측으로 "론 엣지소드S"처럼 게임 쪽 표기가 일관되지 않는 사례를 발견해 정규화 매칭 적용).
- 악보는 별도 창 대신 상위 탭에서 이용합니다. 악기는 제목 아래에서 선택합니다. 작업 실행 중에는 연주 시작을 막으며, 작업 일시정지와 현재 요청 완료 후 연주할 수 있습니다.
- 캐릭터 정보 버튼은 능력치와 재화 패널을 펼칩니다. 주요 재화는 빠른 조회 메뉴입니다. 기존 재화 아이콘 파일과 manifest 매핑은 변경하지 않았습니다.
- 즐겨찾기와 추가 버튼을 제거하고 목록에서 대기열로 드래그하여 추가합니다. 최근 사용은 이 PC에 저장됩니다. 작업 대기열은 앱을 닫으면 유지되지 않습니다.
- 아이템 아이콘은 모비라이프에서 이름이 일치하는 항목만 캐시합니다. 출처는 `app/dashboard/assets/item_icons/manifest.json`에 기록하며, 아직 매핑되지 않은 새 요리·장비에는 임의 아이콘을 표시하지 않습니다.
- 게임 확인 팝업이 감지되면 일시정지하고 사용자가 게임에서 확인한 뒤 재개해야 합니다.
- **창고**(2026-09-19): 계정 전체 아이템 검색기. 검색창에 아이템 이름을 입력하면(부분 일치) `character_data`에 감지된 모든 캐릭터의 인벤토리/캐릭터창고/공용보관함을 뒤져서 `{이름(캐릭터 관리에서 지정 안 했으면 직업)}/{서버명} - {인벤토리|보관함|공용보관함}` 그룹별로 아이템명/수량을 보여줍니다. CLI가 소모품류만 주므로(장비/코스튬/펫 제외) 검색 범위도 그만큼으로 한정됨.

검증: `python -m unittest discover -s tests -v` (게임 명령을 보내지 않는 대기열 테스트).

실행 파일 재빌드는 `50_APP/build.ps1`을 사용합니다. `mabinobi.spec`에서 외부 이미지 도구의 DLL과 Windows API-set 사본이 섞이지 않도록 제외합니다. 일반 명령으로 다시 빌드하면 환경에 따라 `QtCore` 로드 오류가 재발할 수 있습니다.

배포 파일 UI 검사: `마비노비.exe --ui-self-test 결과.json`. 게임에 연결하지 않고 실제 창 생성 결과와 화면 PNG를 저장한 후 종료합니다. 단순 프로세스 생존 여부가 아니라 JSON의 `visible`, `tabs`, `catalog_rows` 및 화면을 확인합니다.

## 실행

```
pip install -r 50_APP/requirements.txt
python 50_APP/main.py
```

또는 프로젝트 루트의 [마비노비.exe](../마비노비.exe)를 더블클릭 — `main.py`를 PyInstaller `--onefile`로 직접 빌드한 완전 독립 실행 파일이라(2026-09-19~) Python도, 이 프로젝트 폴더도 필요 없이 exe 하나만 있으면 바로 실행된다. 빌드는 `50_APP/`에서 `./build.ps1` 실행(권장 — DLL 격리 포함) 또는 직접:
```
python -m PyInstaller --noconfirm --distpath .. mabinobi.spec
```

## 구성

- `main.py` — 진입점. 바로 대시보드로 진입.
- `app/version.py` / `app/updater.py` / `app/dashboard/update_worker.py` — 자동 업데이트(2026-09-19). exe로 빌드된 경우(`sys.frozen`)에만 동작 — 시작 시 백그라운드로 GitHub Releases 최신 태그를 조회해 `app/version.py`의 `APP_VERSION`보다 높으면 조용히 다운로드해뒀다가, 가공 무한/JOB 대기열이 idle일 때 exe 자신을 교체하고 재시작함. GitHub 관련 UI/URL은 사용자에게 전혀 노출되지 않음. 새 버전 배포 절차: `APP_VERSION` 올리기 → exe 재빌드 → GitHub에 `vX.Y.Z` 태그로 Release 생성, `마비노비.exe` 이름 그대로 자산 첨부, Publish.
- `app/cli_client.py` — `MabinogiMobile_CLI.exe` 서브프로세스 호출 래퍼. 경로 우선순위: `MABINOGI_CLI_PATH` 환경변수(개발자용 강제 override) > `set_cli_path()`로 설정된 경로(아래 `cli_setup.py` 참고) > 넥슨 기본 설치 경로. 동시 호출 충돌 방지용 락 포함 — `run_cli()`는 블로킹 획득, `try_run_cli()`는 바쁘면 즉시 `None`(백그라운드 폴링 전용).
- `app/cli_settings.py` / `app/dashboard/cli_setup.py` — MabinogiMobile_CLI.exe 경로 자동 감지(2026-09-19). 기본 경로(`C:\Nexon\MabinogiMobile\`)에 없으면 시작 시 안내 팝업 + 폴더 선택 창을 띄워 설치 폴더를 직접 고르게 하고, `cli_settings.json`(프로젝트 루트, `character_data/`와 같은 위치)에 저장 — exe 자체는 자동 업데이트 때 파일만 교체되고 이 파일은 그대로 남으므로 새 버전에서도 다시 물어보지 않음. `MABINOGI_CLI_PATH`가 설정돼 있으면 이 과정 자체를 건너뜀(개발자 의도를 존중).
- `app/character_profiles.py` / `app/dashboard/character_watcher.py` — 캐릭터 전환 감지(2026-09-19). CLI엔 "지금 캐릭터가 몇 번인지" 알려주는 필드가 없고, 캐릭터/서버/계정 개수에 대한 가정도 두지 않는다(여러 서버·여러 계정에 걸쳐 부캐를 두는 사용자도 있음). 캐릭터 귀속 재화인 냥 토큰/하트 토큰을 2초마다 폴링하다 **둘 다 동시에** 바뀌면 캐릭터가 바뀐 것으로 판단(`try_run_cli`로 폴링해 다른 워커의 CLI 호출을 절대 막지 않음). 전환 감지 시(또는 최초 실행 시) `get_my_info`+`get_items`를 한 번 더 조회해 직업명+서버명+전투력으로 기존 프로필과 매칭(같은 직업·같은 서버 중 전투력 10% 이내면 동일 캐릭터로 간주 — 서버/계정까지 구분해야 다른 서버·다른 계정의 캐릭터가 우연히 같은 직업/전투력이어도 안 섞임)하거나 새로 생성, `character_data/profile_N.json`에 캐릭터 정보/재화/인벤토리/캐릭터창고/계정창고를 전부 저장. 계정창고를 공용 파일 하나로 따로 두지 않고 프로필마다 저장하는 이유: 계정창고는 "같은 계정+같은 서버" 안에서만 공유라서, 파일 하나로 두면 다른 서버·다른 계정 캐릭터가 감지되는 순간 그 데이터로 덮어써져 버림. `profile_N`은 내부 매칭용 키일 뿐, 화면(캐릭터 정보▾/정령의 날개 사이 라벨)엔 항상 `이름(⚔️전투력)` 형태로 표시 — 이름은 `캐릭터 관리`에서 사용자가 바꾸기 전까진 직업명. 계정 전체 아이템 검색기의 데이터 기반. `get_items`가 소모품류만 주므로(장비/코스튬/펫 제외) 저장되는 인벤토리/창고도 그 범위로 한정됨.
- `app/dashboard/character_manager.py` — "캐릭터 관리" 버튼(2026-09-19, 예전 "사용 가이드" 버튼 자리) → 위에서 감지된 프로필 목록(프로필ID/이름, 클래스, 서버, 최종 접속)을 보여주는 비모달 창. 선택한 캐릭터의 표시 이름을 직접 지정("이름 변경")하거나, 이 앱의 로컬 기록만 삭제("삭제" — 실제 게임 캐릭터/아이템엔 영향 없음, 다시 접속하면 새로 쌓임)할 수 있음.
- `app/dashboard/storage_search.py` — "창고" 탭(2026-09-19, 계정 전체 아이템 검색기). 검색어(빈 칸이면 전체 목록)를 `character_profiles.search_items()`(순수 로직)에 넘기고, 결과를 `QTreeWidget` 그룹으로 렌더링: ①"전체 합계"(모든 캐릭터 인벤토리+캐릭터창고+계정창고 합산) → ②"공용보관함"(계정+서버 공유라 캐릭터별 중복 없이 하나만) → ③`{이름}/{서버} - {인벤토리|보관함}`(캐릭터별). 아이템 이름의 `<color=..>...</color>` 같은 리치텍스트 태그는 제거하고 안의 텍스트만 표시(`_clean_name`). "새로고침" 버튼으로 현재 활성 캐릭터의 인벤토리/창고/계정창고만 즉시 재조회 가능. 검색 결과 개수와 무관하게 레이아웃이 안 흔들리도록, "결과 없음" 등은 별도 위젯을 숨기는 대신 트리 안에 안내 행 하나로 표시.
- `app/dashboard/ui_kit.py` — `modern_window.py`/`character_manager.py`/`storage_search.py`가 함께 쓰는 다크 테마 스타일시트(`STYLE`)와 위젯 생성 헬퍼(`heading`/`button`/`table`). 순환 임포트를 피하려고 별도 모듈로 분리.
- `app/dashboard/overlay.py` — 인게임 오버레이 HUD(2026-09-20). 새로고침↔캐릭터 관리 사이 "오버레이" 토글 버튼으로 켜고 끔(게임이 이미 연결돼 있으면 시작 시 자동 on, 연결되는 순간에도 자동 on). 게임 창은 `ctypes`(표준 라이브러리, 신규 의존성 없음)로 `FindWindowW`+`GetClientRect`+`ClientToScreen`만 사용해 위치를 찾을 뿐, 게임 프로세스 자체는 절대 건드리지 않음(과거 리페어런팅 시도가 BlackCipher 안티치트에 막힌 전례가 있어 — README 참고 — 오버레이는 그냥 독립된 최상위 창으로만 구현). 모든 패널은 클릭도 키보드 입력도 항상 아래로 통과(`Qt.WindowTransparentForInput`)하고, 배경은 반투명한 둥근 배지 형태(`WA_TranslucentBackground`). 0.5초마다 게임 창의 위치/크기를 다시 읽어 패널을 재배치 — 사용자가 게임 창을 자유롭게 옮기거나 리사이즈해도 계속 따라감. 첫 버전은 패널 크기를 콘텐츠에 맞춰 동적으로(`adjustSize()`) 잡은 뒤 위치를 계산했는데, 그 계산이 아직 placeholder 텍스트("-/7")로 그려진 크기를 기준으로 이뤄져 실제 데이터가 들어간 뒤(더 길어진 텍스트)와 어긋나 화면 위치가 틀어지는 문제가 있었음(사용자 실측 리포트) — 패널 크기를 `PANEL_SIZE`로 고정해 위치 계산이 항상 게임 창 rect에만 의존하도록 수정. 패널 2종: ①좌중간 "가공 시설" 4줄(금속⚙️/목재🪵/가죽🟤/옷감🧵, 7칸 진행 막대 `▰▱`+완료 개수), ②중상단 "환경 정보"(위치📍/날씨/시간🕐, 날씨는 이모지 매핑 테이블 + 알 수 없는 값은 기본 이모지로 대체 — CLI 문서에 날씨 값 전체 목록이 없어 완전한 매핑은 불가능).
- `app/dashboard/` — 메인 화면. 레이아웃: 상단 컨트롤 바(스탯 4x3 + 게임 연결 토글/캐릭터 관리) → 본문 좌측 재화 컬럼 + 중앙(상: 가공 무한 토글, 하: 음악 플레이어) + 우측 JOB 대기열 컬럼.
  - `main_window.py` — 메뉴바 없음. 앱 실행 시 `connection.py`(백그라운드 스레드)로 게임 연결 자동 시도, 실패 시 `connector_guide.py` 비모달 팝업(게임 내 AI 커넥터 활성화 안내 + 스크린샷 2장). `TopStatsPanel`(전투력/생활력/매력/마도저항/공격력/최대체력/방어력/데코점수/힘/솜씨/지력/행운, 4x3 고정 그리드)이 컨트롤 바 왼쪽에 있음. 중앙은 `QSplitter(Vertical)`로 `GatherPanel`/`MusicPanel` 분할, 오른쪽엔 고정폭 `JobQueuePanel`.
  - `modern_window.py` — 위 "통합 작업 UI" 절에서 설명한 새 진입 화면. `main_window.py`의 `DashboardWindow`를 `LegacyWindow`로 확장해 기존 CLI 워커/재화 에셋을 그대로 재사용하면서 작업/악보 통합 탭 레이아웃을 새로 구성.
  - `equipment_crafting.py` / `recipe_cooking.py` — 요리·장비 제작 JOB(부족 재료 채집 → 제작). `recipe_cooking.py`의 `craft_batch()`(2026-09-20)가 목표 수량을 `craftCount`로 한 번에 몰아서 요청 — `execute_crafting` 호출은 `craftCount`와 무관하게 매번 정령의 날개를 소모하므로, N개를 1개씩 N번 나눠 부르는 대신 시설이 허용하는 한 최대한 한 번에(시설별 상한은 `invalid_count`+`maxCount` 응답으로 실측 학습, `food_crafting_job.py`와 동일 방식) 요청해 낭비를 줄임. `equipment_crafting.py`의 `TOWN_EQUIPMENT`: 마을(임무 게시판 NPC)별로 파는 "제작 스크롤: `<이름>`"이 매핑하는 장비 3종 — 스크롤 하나당 장비 2개가 목표라 제작 JOB 기본 수량이 2개.
  - `item_icons.py` — 모비라이프에서 이름이 일치하는 아이템 아이콘만 캐시(`assets/item_icons/manifest.json`).
  - `job_drag.py` — 통합 작업 UI의 카탈로그→대기열 드래그앤드롭 위젯.
  - `widgets.py` — `ToggleSwitch`, `Toast`, `CurrencyColumn`(왼쪽 세로 스크롤 재화 목록, 일부 항목 숨김/이름 축약 규칙 포함), `classify_cli_result()`(CLI 응답 성공/실패 공용 판정 — 여러 패널이 재사용).
  - `gather_panel.py` — "🔁 가공 무한 시작" 토글 버튼(`altering_routine.py` 실행/정지) + 상태 라벨만 남음. 예전엔 채집 바로가기 버튼 25개도 있었지만 2026-09-18에 JOB 대기열로 이전하면서 제거됨.
  - `altering_routine.py` — "가공 무한" 루틴 본체(`AlteringRoutineWorker`, QThread). 금속/목재/가죽/옷감 4계열을 라운드로빈으로 순회하며 시설별로 회수→채우기. **N단계 범용화(2026-09-20)**: 예전엔 계열당 2단계(강철괴류)에서 멈추도록 고정돼 있었는데, 실제로는 계열마다 7단계(철괴→...→백금강괴 등, `10_RESEARCH/05_altering_full_recipe_chains_2026-09-20.md`)가 있어서 `FAMILIES`(계열)/`Tier`(단계)/`RecipeOption`/`Ingredient` 데이터 모델로 전부 표현하도록 재작성함. 목표 등급은 이제 고정이 아니라 `routine_dashboard.py`의 슬라이더로 계열마다 실시간 지정(`AlteringRoutineWorker.set_target`, 스레드 세이프). 슬롯을 채울 땐 목표 등급부터 0단계까지 내려가며 "지금 만들 수 있는 가장 높은 단계"를 찾는데(`_plan_one_slot`), 목표보다 낮은 단계는 자기 산출물을 "다음 단계 한 바퀴(7슬롯) 분 + 5개" 이상 갖고 있을 때만 그 초과분을 상위 단계 합성에 쓴다 — 그 이하는 예약분으로 보존. 원자재는 7작업분의 5배를 목표로 선제 채집(범위는 예전과 동일 — 3단계 이상에서 새로 필요한 전용 원재료/보조재료는 아직 자동 채집 안 함, 보유분만 소비). `duration_seconds` 옵션으로 유한 시간 후 자동 종료 가능(JOB 대기열의 "가공무한 1시간"이 이걸 사용). `blocked` 응답을 만나면 자동 우회 없이 즉시 정지. 재고 조회(`_inventory_counts`)는 이름별로 `get_items`를 따로 부르는 대신 필터 없이 한 번만 불러 로컬에서 집계 — 7단계로 늘면서 이름 수가 늘어도 CLI 호출 수는 그대로 1번.
  - `tier_target_control.py` — 계열 1개당 목표 등급 슬라이더(`TierTargetControl`, 2026-09-20 신규). `QSlider`(0~6, 단계 수만큼) 아래에 그 계열의 7개 단계 이름을 라벨로 나란히 표시하고 현재 선택된 단계만 굵게/민트색으로 강조 — 슬라이더 눈금만으로는 뭘 의미하는지 알기 어려워서(사용자 지적) 항상 산출물 이름이 보이게 함. `target_changed` 시그널을 `routine_dashboard.py`가 구독해 실행 중인 워커에 실시간으로 반영.
  - `routine_dashboard.py` — "가공 무한" 실행 중 뜨는 독립 창(모던 화면에선 "무한가공소" 탭에 임베드됨). 계열별 목표 등급 슬라이더 4개(`TierTargetControl`) + 시설별 대기열(n/7, 완료 개수 강조) 표시. 예전엔 재료/생산물 전량 테이블이 있었는데 2026-09-20에 슬라이더로 교체(사용자 요청 — 고정 2단계 알고리즘이 실시간 목표 등급 방식으로 바뀌면서, 여기서 보여줄 건 재고 스냅샷보다 "어디까지 만들 것인가"가 됨). `wire_targets(worker)`가 슬라이더 값을 새 워커에 즉시 반영하고 이후 드래그도 계속 그 워커에 꽂아준다 - "가공무한 1시간" JOB처럼 같은 창이 여러 워커를 번갈아 상대하는 경로에서도 이전 워커에 조용히 계속 값을 흘려보내지 않도록. CLI를 직접 호출하지 않고 워커의 `snapshot` 시그널만 구독.
  - `job_queue.py` — 화면 우측 JOB 대기열(`JobQueuePanel`). 유한한 자동화 작업(JOB)을 순서대로 반복 실행(`◀ N ▶` 1~9회), 휴지통으로 삭제(실행 중인 JOB이면 중단 후 다음 진행), `blocked` 시 전체 일시정지+재개. 하단에 검색 가능한 JOB 카탈로그(`JOB_CATALOG`): "가공무한 1시간", "야채볶음10개"/"야채볶음 50개"(`food_crafting_job.py`), "채집: `<이름>` x100" 25종(`gather_job.py`, 예전 채집 바로가기 버튼을 대체), 요리/장비 제작 JOB(`recipe_cooking.py`/`equipment_crafting.py`). `EQUIPMENT_WEEKLY_X6`/`EQUIPMENT_WEEKLY_X10`/`EQUIPMENT_WEEKLY_X5`: 장비 x6/x10/x5 버전 — `JOB_CATALOG`에는 안 넣어서 검색 목록엔 안 뜨고, 제작 탭의 "주간 제작(마을)"/"주간 제작(마을) x5" 버튼에서만 사용.
  - `food_crafting_job.py` — 재료 채집→`execute_crafting` 1회성 JOB 타입(`FoodCraftWorker`). 부족한 재료만 채집 후 목표 개수 제작, 시설의 1회 제작 상한(`invalid_count`+`maxCount`)에 걸리면 자동 분할.
  - `gather_job.py` — 채집 한 번짜리 1회성 JOB 타입(`GatherJobWorker`) + `GATHER_ITEMS`(예전 버튼 목록, 25종).
  - `music_panel.py` — 스포티파이류 플레이어. 좌: 검색창 + 보유 악보 카탈로그(`get_music_scores`, 드래그 소스). 우: 현재 재생 곡 + 재생 대기열(드래그로 순서 변경/카탈로그에서 끼워넣기/휴지통으로 삭제) + 하단 `InstrumentBar`(보유 악기 버튼, 클릭 시 `change_instrument`). 대기열은 게임에 없는 개념이라 `get_activity`의 `Performance.IsPlaying`을 4초 간격 폴링해서 곡이 끝나면 자동으로 다음 곡 재생.
  - `guide_viewer.py` — 예전 "사용 가이드" 버튼이 쓰던 `10_RESEARCH/03_cli_command_reference_*.md` 렌더러. 2026-09-19에 그 버튼을 캐릭터 관리로 교체하면서 지금 화면(`modern_window.py`)에선 더 이상 안 쓰임 — `main_window.py`(레거시, 실제로 띄워지지 않음)에만 배선이 남아있음. `.md` 문서 자체는 `10_RESEARCH`에 그대로 있고 exe 빌드에도 원래부터 포함 안 됐음(`mabinobi.spec` 참고).
  - `assets/currency_icons/` — 게임 내 재화 화면 스크린샷에서 크롭한 아이콘 28개 + `manifest.json`(`get_currencies`의 `DisplayName` 매핑).
  - `assets/item_icons/` — 요리/장비 아이템 아이콘 캐시 + `manifest.json`.
- `build.ps1` / `mabinobi.spec` — exe 재빌드 스크립트/스펙. DLL 검색 경로를 격리해서 외부 이미지 도구의 오래된 Windows API DLL이 번들에 섞이지 않게 함.
- `tools/refresh_item_icons.py` — 모비라이프에서 아이템 아이콘을 다시 받아 `manifest.json`을 갱신하는 도구.

## 알아둘 것

- 정령의 날개를 소모하는 실행형 명령(`execute_gathering`, `execute_altering`, `execute_crafting`)은 **가공 무한 루틴**과 **JOB 대기열**(채집/제작 JOB들)로 실제로 호출된다. 추가/변경 시 [00_SPEC/02_scope_boundaries.md](../00_SPEC/02_scope_boundaries.md)와 공식 세이프가드(사용자 승인, `blocked` 자동 우회 금지)를 그대로 지켜야 한다.
- Claude Code/MCP 채팅 연동(설치 마법사, `30_MCP_SERVER`, `40_ONBOARDING`, `.mcp.json`)은 2026-09-19에 **제거했다** — "채팅으로 Claude에게 요청" 방식은 당분간 지원하지 않기로 함(나중에 다시 붙일 수도 있음). 이 데스크톱 앱은 그 기능 없이도 완전히 독립적으로 동작한다.
- **알려진 한계**: [00_SPEC/03_requirements.md](../00_SPEC/03_requirements.md)가 요구하는 "정령의 날개 하루 소모 상한 설정" 기능이 아직 없다 — 가공 무한 루틴/JOB 대기열 모두 사용자가 직접 정지해야 멈춘다(가공 무한 JOB은 시간제한으로 자동 종료됨).
- 대화형 자유 텍스트 콘솔(`chat_console.py`)은 만들었다가 **제거했다** — 채집/조회 모두 각 패널·JOB이 직접 담당하는 방식으로 대체.
- 게임 창을 앱 안에 재부모화(임베드)하는 기능도 시도했다가 **제거했다** — 안티치트(BlackCipher)에 의해 제대로 동작하지 않는 것으로 판단됨.
- (위 두 가지 다 `git`이 없는 프로젝트라 이전 코드가 필요하면 이 대화 기록에서 복원해야 한다. 자세한 경위는 [CHANGELOG.md](../CHANGELOG.md) 참고.)
