# Changelog

## 2026-09-19 (세 번째 릴리즈: GitHub Release v0.9.2 게시 — 캐릭터 전환 감지/관리/창고 검색/CLI 경로 자동 감지 반영)

- `APP_VERSION`을 `0.9.2`로 올리고 exe 재빌드, 유닛 테스트 66개 + `--ui-self-test`(탭에 새 "창고" 포함 확인) 통과 후 GitHub Release `v0.9.2` 게시(자산명 `MabiNobi.exe`, ASCII)
- 반영된 내용: 바로 아래 항목("캐릭터 전환 감지 + 캐릭터 관리 + 계정 전체 아이템 검색기(창고) + CLI 경로 자동 감지") 전체

## 2026-09-19 (캐릭터 전환 감지 + 캐릭터 관리 + 계정 전체 아이템 검색기("창고") + CLI 경로 자동 감지)

- **배경**: 계정당 여러 캐릭터(심지어 여러 서버·여러 계정)를 오가며 플레이하는데, CLI엔 "지금 어떤 캐릭터인지" 알려주는 필드가 전혀 없음(28개 명령 전수 확인). 최종 목표는 계정 전체 아이템 위치 검색기 — 이번 세션에서 그 토대를 전부 구현함.
- **캐릭터 전환 감지** (`app/character_profiles.py`, `app/dashboard/character_watcher.py`): 캐릭터 귀속 재화인 냥 토큰/하트 토큰을 2초마다 폴링(`try_run_cli`로, 다른 워커의 CLI 호출을 절대 막지 않음)하다가 **둘 다 동시에** 바뀌면 전환으로 판단. 전환 감지 시(또는 최초 실행 시)만 `get_my_info`+`get_items`로 재식별 — 직업명+서버명+전투력(10% 이내)으로 기존 프로필과 매칭하거나 새로 생성, `character_data/profile_N.json`에 저장. 그 사이에도 매 폴링마다 활성 캐릭터의 `get_items`를 다시 확인해서 아이템이 조금이라도 달라지면(`items_changed`) 그 자리에서 파일을 갱신(`refresh_items`) — 캐릭터를 안 바꿔도 데이터가 계속 최신 유지됨(사용자 요청).
  - CLI 동시 호출 충돌(실측 확인된 기존 제약)을 이 폴링이 절대 어기지 않도록 `cli_client.py`에 실제 락을 추가: `run_cli()`는 블로킹, `try_run_cli()`는 바쁘면 즉시 포기.
  - **실측 버그**: `get_my_info`의 스탯 필드가 문서대로 `{DisplayName, Value}` 객체였는데 숫자로 착각해서 두 번째 실행(기존 프로필과 비교하는 순간) `TypeError`로 즉시 죽음 — `_stat()` 헬퍼로 수정.
  - 계정창고를 처음엔 `account_storage.json` 파일 하나로 공용 저장했다가, 사용자 지적("계정/서버 바뀌면 데이터 날아가지 않냐")으로 각 프로필 안에 내장하도록 수정 + 매칭 조건에 서버명 추가(다른 서버 캐릭터가 우연히 같은 직업/전투력이어도 안 섞이게).
- **캐릭터 관리** (`app/dashboard/character_manager.py`, "사용 가이드" 버튼 자리를 대체): 감지된 프로필 목록(프로필ID/이름·클래스·서버·최종접속)을 보여주는 비모달 창. 이름 변경(표시 이름을 직접 지정, 화면 라벨이 직업명 대신 그 이름으로 바뀜), 삭제(이 앱의 로컬 기록만 삭제 — 실제 게임 캐릭터/아이템엔 무관, 문구로 명확히 안내).
- **창고 탭** (`app/dashboard/storage_search.py`): 검색어(빈 칸이면 전체 목록)로 모든 캐릭터의 인벤토리/캐릭터창고/공용보관함을 찾아 ①"전체 합계"(모든 소스 합산) → ②"공용보관함"(계정+서버 공유라 캐릭터별 중복 없이 하나만, user request) → ③캐릭터별 그룹 순으로 표시. 아이템명의 `<color=...>` 같은 리치텍스트 태그는 제거하고 텍스트만 표시. "새로고침" 버튼으로 활성 캐릭터 데이터만 즉시 재조회. 결과 개수가 바뀌어도 레이아웃이 안 흔들리게 "결과 없음"을 별도 라벨 토글 대신 트리 안 안내 행으로 처리.
  - CLI 한계 확인: `get_items`는 소모품/재료류만 주고 장비/코스튬/펫/탈것/도구는 안 줌 — 검색 범위도 그만큼으로 한정(우회 불가, 게임 쪽 AI 커넥터 자체의 한계).
- **CLI 경로 자동 감지** (`app/cli_settings.py`, `app/dashboard/cli_setup.py`): 기본 경로(`C:\Nexon\MabinogiMobile\`)에 CLI가 없으면 안내 팝업 + 폴더 선택 창으로 설치 폴더를 직접 고르게 하고 `cli_settings.json`(프로젝트 루트, `character_data/`와 같은 자리라 자동 업데이트로 exe만 교체돼도 유지됨)에 저장 — 다음 실행부터는 재질문 없음. `MABINOGI_CLI_PATH` 환경변수가 있으면 이 과정 자체를 건너뜀.
- **기타**: 창 크기를 고정값(1500x920) 대신 현재 활성 화면(커서 위치 기준, 멀티모니터 대응)의 80%로 리사이즈+가운데 정렬하도록 변경. `heading`/`button`/`table`/`STYLE` 헬퍼를 `ui_kit.py`로 분리(순환 임포트 회피, `character_manager.py`/`storage_search.py`와 공유).
- 유닛 테스트 66개(신규 31개)로 순수 로직 전부 검증(전환 감지/매칭/이름변경/삭제/아이템 변경 감지/검색·합산·중복제거/태그제거/CLI 경로 우선순위/설정 파일 저장). Qt 다이얼로그가 필요한 흐름(캐릭터 관리 이름변경/삭제, CLI 경로 폴더선택 팝업)은 오프스크린 스크립트로 실제 코드 경로를 직접 실행해 수동 검증.

## 2026-09-19 (두 번째 릴리즈: GitHub Release v0.9.1 게시 — 친구의 요리/장비 제작 UI 재설계 반영)

- 친구가 작업한 `ui-cooking-equipment-20260919` 브랜치(통합 작업 UI — 채집/요리/제작/무한가공소 탭, 드래그앤드롭 대기열, 아이템 아이콘)를 main에 병합. 브랜치가 v0.9.0 이전 커밋에서 갈라져 나가 있어 main.py/README.md/CHANGELOG.md/.gitignore/exe에서 충돌 발생, 전부 수동 해결
- **병합 중 발견/수정한 버그**: 병합 직후 `--ui-self-test`로 실제 창을 띄워보니 `AttributeError: 'DashboardWindow' object has no attribute 'open_wizard'`로 즉시 크래시 — main에서 이미 제거한 "설치 마법사" 버튼을 새 UI(`modern_window.py`)가 여전히 참조하고 있었음. 버튼 제거 후 재검증(스크린샷으로 채집/요리/제작 탭 정상 동작 확인)
- `APP_VERSION`을 `0.9.1`로 올리고 exe 재빌드, 유닛 테스트 20개 전부 통과 확인 후 GitHub Release `v0.9.1` 게시(자산명 `MabiNobi.exe`, ASCII — v0.9.0에서 실측 확인한 자산명 버그 회피)

## 2026-09-19 (첫 실제 배포: GitHub Release v0.9.0 게시 — GitHub 자산명은 ASCII만 허용된다는 것 실측으로 발견/수정)

- 사용자 요청으로 첫 GitHub Release 생성: `APP_VERSION`을 `1.0.0` → `0.9.0`으로 낮춰서 시작(아직 1.0을 붙이기엔 이르다는 판단), exe 재빌드 후 GitHub API로 Release 생성 + `마비노비.exe` 자산 업로드까지 전부 진행(`gh` CLI가 없어서 REST API를 PowerShell로 직접 호출)
- **실측으로 발견한 중요 버그**: GitHub Release 자산(asset) 파일명에 한글을 쓰면 **조용히 씹힌다** — 업로드 시 `name=마비노비.exe` 쿼리파라미터를 줬는데 실제로는 `default.exe`로 저장됨, 이후 PATCH로 한글 이름으로 rename 시도해도 200 OK를 주면서 이름이 그대로 안 바뀜(반면 ASCII 이름으로 rename은 즉시 성공 — 대조 실험으로 원인을 ASCII 제한으로 확정). 이 상태로 뒀으면 `app/updater.py`의 `ASSET_NAME = "마비노비.exe"`가 앞으로 어떤 release를 올려도 영원히 매칭이 안 되는 치명적 버그였음
- 수정: `ASSET_NAME`을 `"MabiNobi.exe"`(ASCII)로 변경. **로컬 파일명에는 전혀 영향 없음** — `apply_update_and_relaunch()`는 다운로드한 파일을 "현재 실행 중인 exe 자신의 이름"으로 저장/교체하는 구조라, GitHub 쪽 식별용 자산명과 사용자 PC의 실제 파일명(`마비노비.exe`, 한글 그대로)은 완전히 분리되어 있었음 — 그래서 이 수정은 자산 식별자 하나만 ASCII로 바꾸면 끝
- 오프라인 테스트를 하드코딩된 `"마비노비.exe"` 대신 `updater.ASSET_NAME`을 참조하도록 수정 + `ASSET_NAME.isascii()` 검증 케이스 추가(이런 실수가 다시 나면 테스트에서 바로 걸리게)
- exe 재빌드 → 잘못 업로드됐던 `default.exe` 자산 삭제 → 올바른 `MabiNobi.exe` 이름으로 재업로드
- **실제 GitHub Release를 상대로 한 진짜 종단 테스트**(모킹 없이): `check_for_update("0.8.0")`가 실제로 `v0.9.0`을 찾아내고 올바른 다운로드 URL을 반환하는지, `check_for_update("0.9.0")`(이미 최신)이 `None`을 반환하는지, `download_asset()`으로 실제 파일을 내려받아 업로드한 것과 바이트 크기가 일치하는지(46,399,174 bytes)까지 전부 실측 확인
- 배포 링크: https://github.com/oupure7-cyber/MABINOBI/releases/tag/v0.9.0

## 2026-09-19 (Claude Code/MCP 채팅 연동 제거 — 설치 마법사 + 30_MCP_SERVER + .mcp.json + 40_ONBOARDING)

- 사용자 요청: "이제 더 이상 Claude에게 요청하는 기능은 지원 안 할 거 같아(나중에 바꿀 수도 있음). 설치 마법사와 그와 관련된 모든 연동 기능은 지금은 제거해줘" — 데스크톱 앱에서 "화면으로 조회/제어"만 남기고, "채팅으로 Claude에게 요청"하는 별개 사용 방식(Claude Code/MCP)은 당분간 완전히 빼기로 함
- 삭제한 것: `50_APP/app/onboarding/`(`wizard.py`, `checks.py`) — Node.js/Claude Code/계정/구독/Python-MCP/`.mcp.json` 연결/게임 커넥터까지 6단계를 화면으로 안내하던 설치 마법사 전체. `50_APP/app/proc_utils.py`(마법사 전용 터미널/URL 오프너, 다른 곳에서 안 씀). `50_APP/app/app_settings.py`(온보딩 완료 플래그만 있던 파일, 이미 게이팅용으로도 안 쓰이고 있었음 — README에 명시돼 있었음). `30_MCP_SERVER/`(MCP 서버 자체). `40_ONBOARDING/`(그 설치 가이드 문서). 프로젝트 루트 `.mcp.json`(MCP 클라이언트 등록 파일)
- `main_window.py`: "설치 마법사" 버튼 + `open_wizard()` + `OnboardingWizard` import 제거. 덤으로 발견한 것 — 게임 연결 토글 옆 라벨이 "MCP 연결"이라고 잘못 붙어 있었음(실제로는 `cli_client.status()`로 게임 CLI 파이프를 직접 확인하는 거라 MCP와 무관, `connection.py` 확인해서 확정) → "게임 연결"로 수정
- `main.py`/`main_window.py` 상단 docstring에서 온보딩 마법사/`40_ONBOARDING`/`30_MCP_SERVER` 언급 정리, 이번 제거의 배경과 "지금은 빼지만 나중에 되돌릴 수도 있다"는 의도를 주석으로 남김
- 남긴 것 (MCP와 무관하게 계속 필요한 것들): `guide_viewer.py`("사용 가이드" 버튼, `10_RESEARCH`의 CLI 명령 레퍼런스를 보여줄 뿐 MCP 서버와 무관 — `cli_client.py`가 CLI를 직접 호출), `00_SPEC`/`10_RESEARCH`/`20_DESIGN`(기획/조사/설계 문서, 라이브 코드가 아니라 그대로 둠)
- 문서 갱신: 루트 `README.md`(폴더 구조 표에서 `30_MCP_SERVER`/`40_ONBOARDING`/`.mcp.json` 행 삭제, exe 설명에서 "설치 마법사" 언급 제거, 현재 진행 상태에 "⏸️ MCP 채팅 연동 - 제거됨" 항목 추가), `50_APP/README.md`(구성 목록에서 `app/onboarding/`/`app/app_settings.py` 항목 삭제, "알아둘 것"에 제거 사실 명시)
- 문법 검사(`py_compile`) 통과, 관련 없는 코드 참조가 남아있지 않은지 `grep`으로 재확인 후 exe 재빌드

## 2026-09-19 (자동 업데이트에 bridge/redirect 예비 로직 추가 — 앱/자산 이름이 바뀌어도 구버전이 안 끊기게)

- 사용자 질문: "배포 프로그램 이름이 바뀌거나 크게 바뀌면 자동 업데이트를 못 해주는 거 아니냐" — 맞는 지적. 바로 위 항목의 자동 업데이트는 `GITHUB_REPO`/`ASSET_NAME`이 이미 배포된 exe 코드에 고정으로 박혀있어서, 나중에 앱 이름/자산 파일명/저장소가 바뀌면 구버전들은 옛날 위치만 계속 찾다가 조용히 업데이트를 영영 못 받게 됨. 실제로 그런 일이 생기기 전에 미리 대비해달라는 요청
- `50_APP/app/updater.py`에 **redirect(다리) 메커니즘**을 선제적으로 추가: `check_for_update`가 release를 진짜 최신 버전으로 취급하기 전에 먼저 `redirect.json`이라는 이름의 첨부 자산이 있는지 확인 → 있으면 그 release는 실제 버전이 아니라 `{"repo": "...", "asset_name": "..."}` 형태의 "포인터"로 취급하고, 그 안에 적힌 새 저장소/자산명으로 다시 조회(`MAX_REDIRECT_HOPS=3`회까지, 순환 리다이렉트 등 이상 상황에서도 무한루프 없이 안전하게 포기)
- 핵심 아이디어: 이 리다이렉트를 "따라가는 코드" 자체를 지금(사용자가 거의 없는 이른 시점) 모든 신규 빌드에 미리 심어두는 것 — 그러면 나중에 진짜로 이름/저장소를 옮겨야 할 때, 예전 위치에 새 exe를 올릴 필요 없이 `redirect.json` 자산 하나만 달린 release를 예전 자리에 게시하면 이미 배포된 모든 구버전이 알아서 새 위치로 옮겨감
- 오프라인 테스트 갱신(`_fetch_latest_release`가 이제 `repo` 인자를 받도록 시그니처 변경됨에 맞춰 모킹 수정) + 새 케이스 2개 추가: 리다이렉트를 실제로 한 번 따라가서 새 저장소/자산으로 최신 버전을 찾아내는지, 순환 리다이렉트가 와도 무한루프 없이 `None`으로 안전하게 포기하는지. 기존 케이스 전부 재확인 통과
- 문법 검사 통과, exe 재빌드

## 2026-09-19 (GitHub Releases 기반 자동 업데이트 — exe가 알아서 최신 버전으로 갈아치움)

- 사용자 요청: 배포한 `마비노비.exe`를 새 버전 낼 때마다 사용자들이 수동으로 재다운로드하지 않고, exe가 스스로 GitHub Release를 확인해서 조용히 업데이트하게 만들 것. 사용자(엔드유저)가 GitHub의 존재 자체를 모르게 — 팝업/URL 노출 없이.
- **새 파일** `50_APP/app/version.py`: `APP_VERSION` 상수 하나. 배포할 때마다 여기 값을 올리고, 같은 버전으로 GitHub Release 태그를 붙이는 게 이후 배포 절차.
- **새 파일** `50_APP/app/updater.py` (stdlib만 사용, PySide6/프로젝트 임포트 없음 — `launcher/launch_mabinobi.py`가 지키던 것과 같은 원칙, 매 실행마다 로드되는 코드라 가볍게 유지):
  - `check_for_update(current_version)`: `https://api.github.com/repos/oupure7-cyber/MABINOBI/releases/latest`를 인증 없이(공개 저장소라 가능) 조회, 태그명(`vX.Y.Z`)을 현재 버전과 비교, draft/prerelease는 무시, `마비노비.exe`라는 이름의 첨부 자산(asset)이 있는 최신 release만 인정. 오프라인/미배포/파싱실패 등 어떤 이유로든 실패하면 예외 없이 그냥 `None` 반환(사용자에게 어떤 것도 보여주지 않음)
  - `download_asset(url, dest)`: 새 exe를 현재 exe와 같은 폴더에 `마비노비.update.exe`로 다운로드(같은 드라이브에 둬야 나중에 원자적으로 이름 교체 가능)
  - `apply_update_and_relaunch(new_exe, current_exe)`: 자기 자신이 실행 중인 exe 파일을 직접 못 바꾸므로, 숨겨진 PowerShell 헬퍼 스크립트를 분리 프로세스로 띄워서 "현재 PID 종료 대기 → 새 exe로 교체(`Move-Item`, 최대 10회 재시도) → 재실행 → 스크립트 자기 자신 삭제" 수행. cmd/.bat 대신 PowerShell을 쓴 이유: exe 파일명 자체가 한글(`마비노비.exe`)이라 cmd 배치파일의 코드페이지 처리가 이를 깨뜨림, PowerShell은 UTF-8(BOM) 스크립트를 있는 그대로 읽음
- **새 파일** `50_APP/app/dashboard/update_worker.py`: `UpdateCheckWorker`(QThread) — 체크+다운로드를 백그라운드에서 수행, 성공 시에만 `update_ready` 시그널 발생(실패/최신 버전인 경우 아무 시그널도 없음 = UI에 아무 일도 없음)
- `main_window.py`: `DashboardWindow` 생성 직후 `_start_update_check()` 호출 — 단, `sys.frozen`이 아니면(즉 `python main.py`로 개발 중 실행하는 경우) 완전히 스킵(교체할 "자기 exe"가 없으므로). 업데이트가 다운로드되면 곧바로 적용하지 않고 5초 간격 타이머로 `gather_panel.is_busy()`/`job_queue_panel.is_running()`을 확인해서 **가공 무한 루틴이나 JOB 대기열이 돌고 있지 않을 때까지 대기** → idle이 되면 작은 토스트("🔄 새 버전으로 업데이트합니다...")만 띄우고 2초 후 `apply_update_and_relaunch` 호출 + `QApplication.quit()`
- 오프라인 테스트: `check_for_update`의 버전 비교/파싱/draft·prerelease 필터/자산명 매칭/네트워크 실패 케이스 전부 모킹으로 검증. 오프스크린 Qt 스모크 테스트로 dev 모드(비frozen)에서 업데이트 체크가 완전히 스킵되는지, JOB/가공무한 실행 중엔 적용이 미뤄지는지, idle이 되면 실제로 `apply_update_and_relaunch`가 호출되는지까지 확인
- **배포 절차에 추가된 수동 단계** (매 버전마다): 1) `50_APP/app/version.py`의 `APP_VERSION` 올리기 → 2) exe 재빌드 → 3) GitHub 저장소에서 새 Release 생성, 태그를 `vX.Y.Z`(같은 버전)로, `마비노비.exe` 파일을 정확히 그 이름으로 자산 첨부 → 4) **Draft가 아닌 Publish 상태로 게시**(draft/prerelease는 무시되게 만들어둠). 실행 중인 구버전 사용자들은 다음 실행 시(또는 idle 상태가 되는 시점) 자동으로 이 Release를 받아 교체됨
- **실측으로 발견/수정한 버그**: PyInstaller onefile은 Windows에서 실제로 프로세스 2개(부트로더+실제 앱, 부모/자식 관계)로 뜨고 둘 다 원본 exe 파일을 잡고 있음(`Get-CimInstance Win32_Process`로 실측 확인) — 처음엔 `os.getpid()`(자식 PID) 하나만 기다렸다가 고쳐서, "해당 exe 경로를 가진 프로세스가 하나도 없을 때까지" 기다리는 방식으로 변경. 격리 폴더에서 실제 exe 2개(현재판/새판)를 복사해두고 헬퍼를 직접 트리거해 교체+재실행까지 되는 것을 foreground 실행으로 실측 검증함
- **한계/미검증 사항**: 헬퍼(PowerShell 스크립트)를 완전히 분리된(detached) 프로세스로 백그라운드에 띄운 뒤에도 앱이 완전히 종료된 후까지 그 헬퍼가 살아남아 작업을 끝마치는지는, 이 작업을 수행한 개발 환경(샌드박스형 도구) 자체가 자신이 띄운 백그라운드 프로세스를 도구 호출이 끝나면 회수해버리는 것으로 보여 안에서는 확실히 재현/검증하지 못함(`CREATE_BREAKAWAY_FROM_JOB` 플래그를 방어적으로 추가는 해둠) — foreground로 직접 실행했을 때는 스왑/재실행/자가삭제까지 전부 문제없이 동작하는 것을 확인함. 실제 배포 후 첫 업데이트가 사용자 PC(이 샌드박스 밖의 일반 Windows 세션)에서도 정말 끝까지 완주하는지는 실사용자 환경에서 한 번 실측 확인이 필요함
- 문법 검사(`py_compile`) 통과

## 2026-09-19 (진짜 단일 파일 exe로 전환 — 얇은 런처 방식 폐기, launcher/ 삭제)

- 사용자 요청: "내가 원했던건 py 파일들 뭐시기들 다 필요없고 exe 있으면 다 동작하게 만드는것이긴해" — 바로 아래 항목("배포용 런처 강화")의 `launcher/launch_mabinobi.py` 방식은 exe가 여전히 시스템 Python을 찾아 `50_APP/main.py`를 대신 실행해주는 "얇은 런처"일 뿐이라, exe 옆에 프로젝트 폴더 전체가 있어야 동작했음 — 이 방식 자체를 폐기하고 `50_APP/main.py`를 PyInstaller로 직접 빌드하는 진짜 단일 파일(onefile) 번들로 전환
- `50_APP/main.py`: `PROJECT_ROOT`를 frozen 여부에 따라 분기 — `sys.frozen`이면 `Path(sys.executable).resolve().parent`(exe 위치), 아니면 기존처럼 `Path(__file__).resolve().parent.parent`. frozen일 땐 `__file__`이 PyInstaller가 임시 폴더에 풀어놓은 경로를 가리켜 의미가 없어서 실행 파일 자기 자신의 위치를 기준으로 삼아야 함(`launcher/launch_mabinobi.py`가 쓰던 것과 같은 패턴)
- 새 빌드 명령(`50_APP/`에서 실행, 결과물은 프로젝트 루트에 생성):
  ```
  python -m PyInstaller --onefile --noconsole --name "마비노비" --distpath .. --add-data "app/dashboard/assets;app/dashboard/assets" --add-data "app/dashboard/AI_CONNECTOR_ON_1.png;app/dashboard" --add-data "app/dashboard/AI_CONNECTOR_ON_2.png;app/dashboard" main.py
  ```
  PySide6/Qt + `app/` 패키지 전체 + 재화 아이콘 28개 + 커넥터 가이드 스크린샷 2장까지 exe 하나(약 45.8MB, 기존 얇은 런처는 약 7.4MB)에 전부 번들링됨
- **검증**: 완전히 빈 임시 폴더(`AppData\Local\Temp\...\standalone_exe_test`)에 `마비노비.exe` 하나만 복사해서 실행 → Win32 API(`EnumWindows`+`GetWindowTextW`, PowerShell P/Invoke)로 실제 "마비노비" 창이 뜨는 것까지 확인. 다른 파일(프로젝트 폴더, Python 등) 전혀 없이 동작함이 실측으로 확인됨
- `launcher/` 폴더 전체 삭제(`launch_mabinobi.py` 포함) — 이제 존재 이유가 없음(빌드도 실행도 `50_APP/main.py`를 직접 사용)
- 알려진 한계(문서화): `설치 마법사`/`사용 가이드` 버튼은 `40_ONBOARDING`/`10_RESEARCH`/`.mcp.json`을 프로젝트 폴더에서 찾는 기능이라, exe만 단독으로 있으면 "못 찾음"으로 우아하게 실패함(Claude Code 연동 전용 기능이라 대시보드 핵심 기능엔 영향 없음)
- 문서 갱신: 루트 `README.md`(마비노비.exe 설명 + `launcher` 행 삭제), `50_APP/README.md`(실행 섹션에서 launcher 언급 제거, 새 빌드 명령 추가), `40_ONBOARDING/01_사용자_설치_가이드.md` 상단 안내(launcher 자동 설치 언급 → "Python/PySide6조차 필요 없이 exe 하나만 있으면 실행" 으로 수정)

## 2026-09-19 (배포용 런처 강화 — Python/PySide6 자동 감지·설치, exe 재빌드)

- 사용자 요청: 일반 사용자가 `마비노비.exe`만 받아도 바로 쓸 수 있도록, 본격 실행 전에 Python/필요 패키지 설치 여부를 확인하고 없으면 설치해주는 흐름 추가
- `launcher/launch_mabinobi.py` 대폭 강화(여전히 stdlib만 사용 — PySide6/프로젝트 임포트 없음, 그래야 PyInstaller 번들이 작고 50_APP이 바뀌어도 재빌드 불필요):
  - Python 탐색(WindowsApps 스텁 제외) 후 없으면 winget으로 자동 설치 제안(사용자 확인 후 진행) → winget도 없으면 python.org 다운로드 페이지를 브라우저로 열어줌
  - `50_APP/requirements.txt`의 패키지(PySide6)가 import되는지 확인, 안 되면 `pip install -r`으로 자동 설치
  - 평소(이미 다 설치된 경우)는 기존처럼 콘솔 없이 즉시 조용히 실행 — 설치가 실제로 필요할 때만 `AllocConsole`로 콘솔을 띄워 진행 상황을 보여줌(안 그러면 몇 분간 멈춘 것처럼 보임)
  - winget/pip 설치 후 PATH가 바로 반영 안 되는 문제 대응: 레지스트리(`HKLM`/`HKCU`의 `Environment`)에서 PATH를 다시 읽어 `os.environ`에 반영(이번 세션 내내 PowerShell에서 수동으로 하던 것과 동일한 처리)
  - 실행 직후 빠른 크래시 감지(2초 후 프로세스 생존 확인) 추가 - 안내 없이 조용히 실패하는 상황 방지
  - 버그 발견/수정: `app_root()`의 unfrozen(스크립트로 직접 실행) 분기가 `launcher/` 폴더 자체를 프로젝트 루트로 착각하고 있었음(`Path(__file__).parent`) — 빌드된 exe(frozen)는 영향 없었지만(그 분기는 `sys.executable`의 부모 디렉터리를 씀, 실제 배포 시 정상), 로컬에서 스크립트로 직접 테스트할 때 즉시 발견됨 → `.parent.parent`로 수정
- 다른 프로그램/프레임워크가 더 필요한지 점검: 없음 — Windows 10/11엔 PySide6/Qt가 요구하는 C 런타임이 이미 기본 포함되어 있어 VC++ 재배포 패키지 등 추가 설치가 필요 없음. Node.js/Claude Code/mcp 패키지는 Claude Code 채팅 연동(`30_MCP_SERVER`) 전용이라 데스크톱 앱 실행엔 무관 — `40_ONBOARDING/01_사용자_설치_가이드.md` 상단에 이 구분을 명시
- `python launcher/launch_mabinobi.py`로 직접 실행 + `마비노비.exe` 더블클릭(`Start-Process`) 둘 다 실제로 `50_APP/main.py`가 정상 기동되는 것까지 라이브 확인. 오프라인 단위 테스트로 `resolve_python`/`requirements_satisfied`(정상 패키지 및 존재하지 않는 가짜 패키지 케이스)/`refresh_path_from_registry`/`app_root()` 검증
- exe 재빌드(`python -m PyInstaller --onefile --noconsole --name "마비노비"`), 프로젝트 루트에 커밋
- 문법 검사 통과

## 2026-09-19 (스탯 패널 아이콘 → 크롭 대신 전부 이모지로 단순화)

- 사용자 요청: 바로 직전에 스크린샷에서 크롭한 9개 아이콘 파일은 빼고, 12개 스탯 전부 이모지로 통일
- `50_APP/app/dashboard/assets/stat_icons/`(9개 PNG, 이번 세션에 만든 것이라 바로 삭제) 제거, `main_window.py`에서 `QPixmap`/`STAT_ICON_DIR`/`STAT_ICON_FILES` 관련 로직 전부 제거
- `STAT_EMOJI`를 12개 스탯 전부 커버하도록 확장: 전투력🏆/생활력🌿/매력💖/마도저항🔮/공격력🗡️/최대체력❤️/방어력🛡️/데코점수👑/힘👊/솜씨🤚/지력🧠/행운🍀 — 전부 서로 다른 이모지
- `_make_stat_icon`을 이모지 텍스트만 설정하는 형태로 단순화
- 테스트도 이모지 전용 검증으로 교체(12개 전부 서로 다른 이모지 매핑 확인) 후 재실행, 통과
- 스크린샷 원본(`MabinogiMobile_2026091900072704.png`)은 사용자가 직접 삭제 예정

## 2026-09-19 (상단 스탯 패널에 아이콘 추가 — 사용자 스크린샷에서 크롭)

- 사용자가 프로젝트 루트에 넣어둔 본인 "내 정보" 화면 스크린샷(`MabinogiMobile_2026091900072704.png`)에서 스탯 아이콘을 픽셀 좌표로 크롭해 `50_APP/app/dashboard/assets/stat_icons/`에 9개 저장: `ArcaneResistance`(마도저항, 소용돌이 방패), `AttackPower`(공격력, 단검), `DefencePower`(방어력, 방패), `DecorScore`(데코점수, 왕관), `STR`(힘, 주먹), `DEX`(솜씨, 손+반짝임), `INT`(지력, 구름/뇌), `LUCK`(행운, 네잎클로버). `HealthMax`(최대체력)는 스크린샷에 정확히 일치하는 아이콘이 없어서 가장 근접한 "추가체력" 하트 아이콘으로 대체
- `CombatScore`(전투력)/`LivingScore`(생활력)/`AttractivenessScore`(매력)는 스크린샷에 색깔 알약 배경만 있고 아이콘 글리프 자체가 없어서 이모지로 대체: ⚔️/🌿/💖
- `main_window.py`의 `TopStatsPanel`: 기존 세로 2줄(이름/값)짜리 칸을 가로로 확장해 왼쪽에 22px 아이콘(또는 이모지)을 추가 — "{아이콘} {이름}/{값}" 형태
- 오프라인 테스트: 12개 스탯 전부 아이콘 파일 또는 이모지 매핑이 있는지, 아이콘 파일이 실제로 존재하는지, `TopStatsPanel`이 각 칸에 올바른 픽스맵/이모지를 설정하는지 검증. 기존 회귀 테스트 재확인
- 문법 검사 통과

## 2026-09-19 (가공 무한 버튼 라벨 정리 — 캐릭터 세팅 문구를 버튼 위 경고 라인으로 분리)

- 사용자 요청: 버튼 이름에 끼워져 있던 "(티르코네일+숲길잡이+흰까마귀+검술)"을 빼고, 버튼 위에 별도 주의 문구로 표시
- `gather_panel.py`: `STEEL_HINT_TEXT`(⚠️ 티르코네일+숲길잡이+흰까마귀+검술로 세팅해두면 효율이 더 높아요!)를 버튼 바로 위에 주황색 라벨로 추가, 버튼 텍스트(`STEEL_BTN_IDLE_TEXT`)에서는 해당 문구 제거

## 2026-09-19 (JOB 이름 변경 — "야채볶음10개"/"야채볶음 50개" → "요리: 야채 볶음 x10"/"x50")

- 사용자 요청으로 야채볶음 JOB 2종의 표시 이름을 "채집: `<이름>` x100" 네이밍 규칙과 통일되는 형태로 변경: `요리: 야채 볶음 x10` / `요리: 야채 볶음 x50`(key는 그대로 `veggie_stir_fry_10`/`_50`, 실제 게임 레시피 이름 "야채볶음"도 그대로 - 표시 이름만 변경)
- 관련 오프라인 테스트(카탈로그 검색 필터 포함) 갱신 후 재실행, 통과

## 2026-09-19 (악기 바 여러 줄 자동 줄바꿈 + 재화 리스트 행 높이 축소)

- 사용자 요청 1: 음악 패널 하단 악기 변경 바가 가로 스크롤 1줄이라 악기가 늘어나면 다 안 보임 → 화면 폭에 맞춰 자동으로 여러 줄로 줄바꿈되게 변경, 지금은 2줄 정도지만 더 늘어나는 것도 감안
  - `widgets.py`에 Qt 공식 "Flow Layout" 레시피를 `FlowLayout` 클래스로 재도입(2026-09-18에 안 쓴다고 지웠던 걸 이번엔 실제로 계속 사용) — 가로로 채우다 남은 폭이 부족하면 다음 줄로 넘어가고 `heightForWidth`로 전체 높이를 보고하는 표준 Qt 패턴
  - `music_panel.py`의 `InstrumentBar`: 기존 `QHBoxLayout`+가로 스크롤(높이 56px 고정) → `FlowLayout`+세로 스크롤(최대 120px, 그 이상이면 스크롤)로 교체. 악기 몇 개든 폭에 맞게 줄바꿈되고, 너무 많아지면(4줄 이상) 패널을 잠식하지 않고 세로 스크롤로 전환
- 사용자 요청 2: 좌측 재화 리스트 각 항목(entry) 높이가 너무 높아서 스크롤이 과함 → 행 높이 축소 + 아이콘을 가로세로 80%로 축소
  - `widgets.py`의 `CurrencyColumn`: 아이콘 26px → 21px(80%), 칩 내부 상하 패딩 6px → 3px, 리스트 항목 간 세로 간격 6px → 3px
- 오프스크린 테스트로 검증: `FlowLayout`이 폭이 좁아지면 실제로 여러 줄(y좌표가 다른 행)로 나뉘는지, `InstrumentBar`가 9개 악기를 `FlowLayout`으로 무사히 렌더링하는지, `CurrencyColumn` 아이콘이 정확히 21px이고 행 패딩이 줄었는지. 기존 회귀 테스트 전부 재실행해서 이상 없음
- 문법 검사 통과

## 2026-09-18 (채집 바로가기 버튼 25개 제거 → 전부 JOB으로 이전)

- 사용자 요청: 화면 중앙의 채집 바로가기 버튼 그리드(25개, 단단한 통나무 등)를 없애고, JOB 대기열이 생겼으니 각 버튼의 기능을 JOB으로 하나씩 만들 것. JOB 이름은 "채집: `<이름>` x100" 형식(동작+횟수가 이름에 드러나게)
- **새 파일** `gather_job.py`: `GatherJobWorker`(1회성 — `execute_gathering` 한 번 호출하고 끝, 한 번에 최대 100개는 게임 자체 상한과 동일) + `GATHER_ITEMS`(예전 버튼 목록 25종, 그대로 이전). 여러 번 캐고 싶으면 JOB 대기열의 `◀ N ▶` 반복 스테퍼를 쓰면 됨 — JOB 자체엔 내부 반복 루프를 넣지 않음(다른 JOB 타입들과 동일한 설계 원칙)
- `job_queue.py`의 `JOB_CATALOG`에 25개 전부 등록: `f"채집: {item} x100"`. 클로저 캡처 버그(반복문 안에서 lambda로 바로 캡처하면 전부 마지막 아이템을 가리키게 되는 흔한 함정) 피하려고 `_make_gather_job(display_name)`이 팩토리를 반환하는 팩토리 패턴 사용
- `gather_panel.py` 대폭 축소: `CliCallWorker`/`GATHER_ITEMS`/`GRID_COLUMNS`/`_quick_gather`/`_lookup_gatherable`/`_on_gather_done`/`_set_busy`(더 이상 비활성화할 버튼이 없음) 전부 제거. 이제 "🔁 가공 무한 시작" 토글 버튼과 상태 라벨만 남음 — `is_busy()`도 `_steel_worker` 하나만 체크하도록 단순화
- 문서 정리: `50_APP/README.md`가 그동안 밀려있던 것도 이 참에 정리(이미 삭제된 `steel_routine.py` 언급, JOB 대기열/`altering_routine.py`/`food_crafting_job.py`/`gather_job.py`/`routine_dashboard.py` 미기재 등). 루트 `README.md`의 "채집 바로가기 25종" 표현도 갱신
- 오프라인 테스트: `GatherJobWorker` 성공/blocked/일반실패 3가지 + 카탈로그 25종 전부 정확한 이름·워커로 등록됐는지 검증. 기존 JOB 대기열/재료채집제작/가공무한/대시보드 회귀 테스트 전부 재실행해서 이상 없음(카탈로그 개수가 3→28로 바뀐 것 반영해서 테스트 assertion 갱신)
- 문법 검사 통과

## 2026-09-18 (JOB 2종 추가 — "야채볶음10개"/"야채볶음 50개", 재료 채집→제작 JOB 타입 신설)

- 사용자 지정 레시피: 야채볶음 10개 = 감자 80 + 양파 30 + 양배추 60 + 허브 20 (실측값). 50개는 5배(감자 400/양파 150/양배추 300/허브 100). `get_gatherable_items`로 감자/양파/양배추/허브 전부 채집 가능, 정확한 DisplayName 확인(띄어쓰기 없는 "감자" 등 그대로)
- **새 JOB 타입** `food_crafting_job.py`(`FoodCraftWorker`): `AlteringRoutineWorker`(7슬롯 가공 대기열)와는 다른 형태 - `execute_crafting`은 이동+제작+수령이 한 호출로 끝나는 구조라, 부족한 재료를 먼저 다 채집한 뒤 목표 개수만큼 제작하고 끝나는 **1회성 워커**로 설계(내부 반복 없음 - 여러 번 돌리고 싶으면 JOB 대기열의 `◀ N ▶` 스테퍼를 쓰면 됨)
  - 재료 부족분만 채집(이미 충분하면 채집 안 함), 재료 다 모이면 `execute_crafting` 호출 - 시설별 1회 최대 제작 횟수 제한(`invalid_count`+`maxCount`)에 걸리면 그 한도를 기억해서 자동으로 여러 번에 나눠 요청(예: 50개 요청 시 한도가 20이면 20+20+10)
  - 다른 워커들과 동일한 안전장치: `blocked` 뜨면 즉시 멈추고 사용자에게 안내, 자동 클릭 없음
- `job_queue.py`의 `JOB_CATALOG`에 `"야채볶음10개"`/`"야채볶음 50개"` 등록(사용자가 붙인 이름 표기 그대로 - 띄어쓰기 불일치 포함)
- 오프라인 테스트 5가지로 검증: 재료 충분 시 채집 스킵하고 바로 제작, 부족 재료만 채집 후 제작, 시설 제작 한도 학습 후 자동 분할(50=20+20+10), 채집 중 `blocked` 시 제작 시도 자체를 안 하는지, 카탈로그 등록값이 정확히 5배 스케일인지. 기존 JOB 대기열/가공 무한 회귀 테스트 전부 재실행해서 이상 없음
- 문법 검사 통과. 라이브 실행은 아직 미검증

## 2026-09-18 (JOB 대기열 신설 — 화면 우측 컬럼, 최초 JOB "가공무한 1시간")

- 사용자 요청: 유한한 동작 묶음(JOB)을 대기열에 쌓아두고 순서대로 하나씩 처리하는 새 기능. 화면 우측 컬럼(창 폭 1100→1450으로 확대), 최상단에 현재 JOB 이름, JOB마다 `◀ N ▶`(1~9) 반복 횟수 표시, 현재 JOB이 1회 끝날 때마다 자동 감소·0이면 다음 JOB으로, 드래그해서 휴지통에 놓으면 삭제(현재 JOB이면 중단 후 다음 JOB 진행), 하단에 곡 검색과 유사한 JOB 카탈로그 검색
- **JOB의 정의를 그대로 구현**: "가공 무한에 1시간 타이머를 넣으면 JOB이 된다"는 설명을 살려서, `AlteringRoutineWorker`에 `duration_seconds` 옵션을 추가(기존 무한 루틴은 `None`으로 그대로 무한 동작, 기존 "가공 무한" 버튼은 영향 없음). 시간 초과는 각 액션 사이(스윕 시작 전, 채집 루프 반복마다)에서 체크 - 진행 중인 단일 액션(최대 15분짜리 채집 등) 도중엔 끊지 않으므로 실제 종료는 설정 시간보다 최대 그만큼 늦어질 수 있음
- **새 파일** `job_queue.py`: `JobSpec`(카탈로그 항목: 이름 + 워커 팩토리) / `QueuedJob`(대기열 항목: spec + 1~9 반복) / `JobQueuePanel`(오케스트레이션 전체). 카탈로그에 `"가공무한 1시간"` 1건 등록(`AlteringRoutineWorker(duration_seconds=3600)`) — 이후 새 JOB 타입은 같은 모양(status/blocked/stopped 시그널 + request_stop())의 워커 팩토리만 카탈로그에 추가하면 됨
  - 대기열 리스트는 **현재 실행 중인 JOB(0번 행, 강조 표시)과 대기 중인 JOB**을 한 `QListWidget`에 같이 렌더링, 매번 전체를 지우고 다시 그리는 방식(`_render`)으로 통일 — `setItemWidget`(◀▶ 버튼이 들어간 커스텀 행)이 Qt의 내부 드래그 재정렬과 결합하면 위젯이 엉뚱한 행에 남는 문제가 잘 알려져 있어서, 대기열 내부 순서 변경 드래그는 아예 지원하지 않기로 함(사용자가 명시적으로 요구한 건 휴지통 삭제뿐이었음) — 카탈로그→대기열 드롭(끝에 추가)과 대기열→휴지통 드롭(삭제)만 허용
  - 버그 발견/수정(오프라인 테스트 중): 반복 횟수가 남은 채로 한 번이 끝나면 `_current`는 유지하고 `_current_worker`만 `None`이 되는데, `_maybe_start_next`의 가드 조건이 `_current is not None`이었어서 다음 반복을 위한 새 워커를 아예 시작 안 하던 문제 → 가드를 `_current_worker is not None`(실제로 뭔가 돌고 있는지) 기준으로 수정
  - `blocked`(게임 확인 필요) 발생 시 반복 감소/다음 JOB 진행 없이 **대기열 전체를 일시정지** — 기존 단일 루틴의 안전장치를 대기열 레벨까지 확장. "▶ 재개" 버튼으로 같은 JOB을 그대로 재시도
  - `gather_panel.py`의 수동 "가공 무한"/채집 버튼과 상호 배제: `GatherPanel.is_busy()`를 JOB 시작 전에 확인하고, 사용 중이면 3초 간격으로 재시도(CLI 동시 호출 충돌 방지, 기존 제약과 동일선상). 반대 방향도 체크(가공 무한/채집 버튼도 JOB 대기열 실행 중이면 거부)
- `main_window.py`: 창 크기 확대, 우측에 `JobQueuePanel` 고정폭(320px) 컬럼 추가, `gather_panel`과 상호 참조 연결
- 오프라인 테스트 2개 파일, 14개 시나리오: 가짜 워커(실제 스레드/CLI 없이 동기 동작)로 큐 오케스트레이션 9가지(자동 시작/반복 유지/다음 JOB 전환/대기 삭제/현재 삭제=중단/중단 후 다음 진행/blocked 일시정지+재개/gather_panel 사용 중 대기) 전부 검증 - 위 재시작 버그를 여기서 발견. 실제 카탈로그를 쓰는 UI 스모크 테스트 5가지(검색 필터, 실제 `AlteringRoutineWorker` 기동/정지, `DashboardWindow` 전체 배선, 창 폭)도 통과
- 문법 검사 통과. 라이브 실행(실제 화면에서 드래그앤드롭 동작)은 아직 미검증

## 2026-09-18 (대시보드에 완료된 대기열 개수 표시)

- 사용자 질문: 대시보드가 "n/7"(진행중+완료 합계)만 보여줘서, 그중 몇 개가 실제로 완료돼서 회수 대기 중인지 구분이 안 됨
- `AlteringRoutineWorker`가 `get_altering_works` 응답을 파싱할 때 이미 `State: Completed`를 알고 있었으므로, `snapshot` 신호에 `queue_completed`(시설별 완료 개수) 필드 추가 — 새 CLI 호출 없이 기존 데이터 재사용
- `routine_dashboard.py`: 완료분이 있으면 대기열 라벨에 "· 완료 N개 회수 대기"를 덧붙이고 글자색을 강조(주황)해서 한눈에 띄게 표시. 0개면 평범한 텍스트로 표시
- 오프스크린 테스트로 완료 개수 표시/미표시 둘 다 확인, 기존 회귀 스위트 재실행해서 이상 없음. 문법 검사 통과

## 2026-09-18 (채집 버퍼 5배 확대 + 철광석/광석 왕복 낭비 방지)

- 사용자 피드백: "할일 없어서 노는시간이 너무 길다" → 채집 목표치를 2배에서 5배로 확대(`RAW_MATERIAL_BUFFER_MULTIPLIER`). 그 과정에서 기존 코드의 숨은 문제 발견: 채집 트리거 조건이 `current <= reorder`(1배)였는데 `target`(2배)은 후보 우선순위 계산에만 쓰이고 실제 "언제까지 채집할지"에는 전혀 관여하지 않고 있었음 — 즉 1배만 넘기면 바로 그 재료는 채집 후보에서 빠져서, target을 아무리 올려도 실질적 효과가 없는 구조였음. 1배/2배 2단계 구분을 없애고 `current < target`(이제 5배) 하나로 단순화 — 목표치에 도달할 때까지 계속 채집
- 사용자 피드백: "철 광석/광석은 캐러가는데 시간이 너무 오래 걸려서, 왔다갔다 하는 시간 안 아깝게" → 이 둘을 채집할 때는 목표치 도달 여부와 무관하게 한 번 갈 때 `execute_gathering`을 2번 연달아 호출(`LONG_TRAVEL_GATHER_REPEAT`, 최대 200개). 다른 재료는 그대로 1회
- 오프라인 검증: 재료가 넉넉해도(구 2배 기준으로는 "충분") 이제 5배 목표치까지 채집을 계속 이어가는지, 철 광석을 캐러 갈 때 정확히 2번씩 연달아 호출되는지 확인. 기존 회귀 스위트(3개 테스트 파일) 전부 재실행해서 이상 없음 확인
- 문법 검사 통과. 라이브 실행은 아직 미검증

## 2026-09-18 ("가공 무한" 독립 대시보드 창 추가 — 자원 현황 + 대기열 채움 현황)

- 사용자 요청: 루틴 실행 중 별도 창으로 재료/생산물 전량(인벤토리+캐릭터창고+계정창고 합계)과 4개 시설의 대기열 채움 현황(n/7)을 실시간으로 보여줄 것
- **CLI 동시 호출 충돌 회피가 핵심 설계 제약**: 이 프로젝트는 이미 "같은 `MabinogiMobile_CLI.exe`를 두 워커가 동시에 호출하면 충돌한다"는 제약이 있어서(채집 버튼과 가공 루틴이 서로 잠그는 이유), 대시보드가 스스로 주기적으로 CLI를 폴링하는 방식은 채택하지 않음. 대신 `AlteringRoutineWorker`에 `snapshot` 시그널(`{materials, queue}`)을 추가해서, 루틴이 **자기 판단을 위해 이미 가져오던 데이터**를 그대로 흘려보내는 방식으로 구현(`altering_routine.py`) — 새로운 CLI 호출 없음
  - 스윕 시작 시(전체 재고+대기열 스냅샷), 회수 성공/실패 시, 가공 등록 성공 시, 채집 성공 시마다 `snapshot` 발행 — 대시보드가 액션 단위로 거의 실시간에 가깝게 갱신됨
  - 재료 트래킹을 함수-로컬 스크래치 dict에서 워커 인스턴스에 상주하는 `self._materials`/`self._queue_occupied`로 변경. `_plan_fill`이 미리 몇 수 앞의 소모량을 계획하더라도, 실제 소모 반영은 **해당 단계의 `execute_altering` 호출이 진짜로 성공한 뒤에만** 적용(`consumption` 딕셔너리를 계획과 분리) — 계획된 7개 중 3번째에서 `blocked`가 나면 4~7번째의 (실행되지도 않은) 소모량이 재고에 잘못 선반영되는 사고를 방지
  - **버그 발견/수정**: 기존 코드는 회수(`complete_altering_work`)가 드물게(비-`blocked`) 실패해도 해당 시설의 여유 슬롯을 "완료분은 제외한 진행중 개수"만으로 계산해서, 실제로는 완료품이 여전히 슬롯을 차지하고 있는데도 새 가공을 등록하려 시도할 수 있었음 — 회수 실패 시 그 완료분 개수를 `remaining_completed`로 남겨 슬롯 계산에 반영하도록 수정
  - 표시 대상 확대: 기존 의사결정용 12개 재료(중간재+직접재료+원자재)에 완제품 4종(강철괴/목재+/옷감+/가죽+)도 추가해 총 16개 항목을 추적(`ALL_MATERIAL_NAMES`)
- **새 파일** `routine_dashboard.py` — `RoutineDashboard`(QWidget, `Qt.Window` 플래그로 마비노비 메인 창과 독립된 최상위 창, 기본 타이틀바로 드래그 가능): 재료 16종 표(그룹박스 안 `QTableWidget`), 시설별 대기열 `QProgressBar`(0~7) + 라벨. `attach(worker)`로 `snapshot`/`blocked`/`stopped` 시그널만 구독 — CLI 미호출
  - `blocked` 수신 시: 재료 표/대기열 섹션을 숨기고, **빨간 굵은 글씨 알림**("가공 무한 루틴이 자동으로 중단되었습니다 - 사유: {kind}")으로 교체. 이후 들어오는 `snapshot`은 무시(멈춘 상태의 숫자가 계속 갱신되는 척하지 않도록)
  - `stopped` 수신 시: 직전에 `blocked`가 있었으면(자동 중단) 창은 그대로 유지, 없었으면(사용자가 정지 버튼을 누른 경우) 창을 스스로 닫음(`WA_DeleteOnClose`)
- `gather_panel.py`: "가공 무한 시작" 버튼 클릭 시 워커 생성 직후 `RoutineDashboard`를 생성해 `attach()`하고 `show()` — 메인 창(`self.window()`)을 부모로 지정하되 별도 최상위 창이라 자유롭게 이동 가능. 대시보드가 닫히면 `destroyed` 시그널로 참조 정리
- 오프라인 검증: (1) 스윕 한 번에 빈 대기열 7칸을 채우는 동안 `snapshot`이 8회(초기 1 + 등록 7) 발행되고 마지막 스냅샷의 재료/대기열 수치가 정확한지, (2) 회수가 `timeout`으로 실패했을 때 그 시설에 새 가공을 전혀 등록하지 않고 `_queue_occupied`가 7로 유지되는지(위 버그 수정 검증) — 둘 다 assert로 통과. 대시보드 자체도 오프스크린으로 스냅샷 반영/블락 알림 전환/블락 후 무시/수동 정지 시 자동 닫힘/`GatherPanel`에서 루틴 시작 시 대시보드 자동 생성까지 5개 시나리오 전부 통과
- 문법 검사 통과. 라이브 실행(실제 창 두 개 동시 확인)은 아직 미검증 — 사용자가 직접 앱에서 테스트 예정

## 2026-09-18 ("가공 무한" 스케줄링 알고리즘 재설계 — 그리디 채우기 + 시설별 순차 처리 + 채집 버스트)

- 사용자 피드백 3가지 반영, 기존 1배/2배 중간재 버퍼 히스테리시스(완제품보다 중간재 보충 우선)는 폐기:
  1. **그리디 상위 우선 채우기**: 빈 슬롯이 있으면 상위 가공(완제품)을 재료가 허락하는 한 최대한(최대 7칸까지) 채우고, 상위 재료가 떨어지면 남은 슬롯을 하위 가공(중간재)으로 끝까지 채움 — 예전엔 틱당 액션 1개(`_tick`)라 슬롯 하나 채우고 다음 루프까지 기다렸는데, 이제 `_plan_fill`이 한 시설당 여러 번의 `execute_altering`을 한 번의 스윕(`_sweep_all_facilities`) 안에서 연달아 호출
  2. **시설별 순차 처리로 루프 순서 변경**: 회수 4곳 먼저 → 채우기 4곳 나중이 아니라, 시설 A 회수 → A 끝까지 채우기 → 시설 B 회수 → B 채우기 순서로 중첩 루프 순서를 뒤집음(`_sweep_all_facilities` 안에서 체인별로 회수+채우기를 한 번에 끝냄)
  3. **채집 버스트 + 3/4 임계값**: `execute_gathering` 한 번(최대 100개, 약 2분)이 끝나면 무조건 다음 채집으로 넘어가지 않고 `_count_ready_facilities()`로 회수 가능한 시설 수를 확인 — 4개 중 3개 이상이 준비되면 채집을 멈추고 회수+재충전 라운드로 전환, 3개 미만이면 회수하러 가는 왕복이 아직 아깝다고 보고 채집을 계속 이어감(`_gather_until_worth_a_collection_trip`)
- 상위/하위 우선순위가 뒤집혀서, 이제 완제품 재료(철괴/석탄 등)가 있는 한 무조건 소진할 때까지 쓰고 중간재 재고를 보호하지 않음 — 사용자가 명시적으로 이렇게 바꿔달라고 요청함
- 오프라인 시뮬레이션 5가지 케이스(가짜 `run_cli`로 인벤토리/대기열 상태를 실제로 변화시키는 페이크 게임 상태까지 구현)로 assert 검증: 빈 대기열이 한 스윕에 7칸 전부 채워지는지, 상위 재료 소진 후 하위로 정확히 전환되는지, 회수→채우기가 시설별로 인터리빙되는지(다른 시설 회수가 끼어들지 않는지), 아무것도 준비 안 됐을 때 채집이 여러 번 연달아 이어지는지, 3/4 준비되면 채집 1번만 하고 바로 회수로 전환하는지. 기존 가죽 체인 스킵 로직도 회귀 확인. 전부 통과
- 문법 검사 통과. 라이브 실행은 아직 미검증 — 사용자가 직접 앱에서 테스트 예정

## 2026-09-18 ("가공 무한" 4종 동시 루틴으로 확장 — 강철괴/목재+/옷감+/가죽+, 상태 표시 개선)

- 사용자 요청: 강철괴뿐 아니라 목재+/옷감+/가죽+도 같은 방식으로, 네 가공 시설(금속/목재/옷감/가죽)의 대기열이 동시에 놀지 않게 관리
- 레시피 실측/확인: 목재+ x3←목재 x3+나무 진액 x4, 목재 x3←통나무 x10(사용자 제공); 옷감+ x3←옷감 x3+양털 x4(사용자 제공), 옷감 x3←양털 x10(목재/가죽 체인과 동일 구조로 가정 — 양털 재고가 항상 충분해 `get_alterable_items`가 정확한 값을 보여준 적이 없어 미실측, 코드 주석에 명시); 가죽+ x3←가죽 x3+타닌 가루 x4, 가죽 x3←생가죽 x10(사용자 제공). `get_gatherable_items`로 나무 진액/철 광석/광석/통나무/양털은 채집 가능, **타닌 가루/생가죽은 채집 목록에 아예 없음**(빈 배열)을 확인 — 사용자가 말한 "생가죽은 채집 불가"와 일치
- `steel_routine.py` → `altering_routine.py`로 교체 (강철괴 전용 `SteelRoutineWorker`를 `AlteringRoutineWorker` + `Chain`/`IntermediatePath` 데이터클래스로 일반화). CLI를 동시에 두 워커가 호출하면 충돌하는 기존 제약(2026-09-18 "대화 콘솔 제거" 항목) 때문에 4개를 진짜 병렬 스레드로 돌리지 않고, **워커 하나가 매 틱 4개 시설을 라운드로빈으로 훑어 가장 급한 액션 하나만 수행**하는 방식으로 구현 — 매 틱 시작 시작 인덱스를 회전시켜 특정 체인이 계속 뒤로 밀리지 않게 함
  - 버퍼 규칙(강철괴와 동일한 1배/2배 원자재 버퍼, 중간재 21/42 우선순위)을 모든 체인에 동일 적용. 옷감 체인은 양털이 직접 재료(옷감+, 4개)와 중간재 원료(옷감, 10개) 양쪽에 다 쓰여서 버퍼 요구량을 합산(4+10=14, 7배=98/14배=196)해서 관리
  - 가죽 체인: 타닌 가루/생가죽 둘 다 채집 불가라는 게 확인돼서, 이 둘은 절대 채집하지 않고 창고 보유분만 소비. 생가죽 총 보유량(인벤토리+캐릭터+계정창고)이 10개 미만이면 가죽 체인 자체를 매 틱 스킵(사용자 지정)
  - 버그 수정: "완제품을 못 만들면 중간재라도 만든다" 폴백에 상한이 없어서, 가죽+가 타닌 가루 부족으로 영영 막힌 상태에서도 가죽을 무한정 계속 가공해 정령의 날개만 낭비하는 문제를 오프라인 시뮬레이션 중 발견 → 중간재가 이미 자기 2배 목표치(42) 이상이면 더 이상 만들지 않고 "막힘"으로 보고하도록 상한 추가
- **상태 표시 개선**(사용자 요청 — "멍하니 기다리는 이유를 알고 싶다"): `execute_altering`/`execute_gathering`/`complete_altering_work` 등 실제 게임 내 시간이 걸리는 모든 액션 직전에 "⏳ 지금 뭘 하는 중"을 먼저 띄우도록 변경(이전엔 완료된 뒤에만 결과가 떴어서, 최대 몇 분씩 걸리는 동안 화면엔 지난 틱 메시지만 남아있었음). 정말 할 일이 없을 때도 체인별로 "대기열 가득" / "스킵(사유)" / "여유 N칸인데 OO가 없어서 채집도 불가"까지 구체적으로 표시
- **UI**: 상태 라벨을 채집 버튼 그리드 아래(음악 패널과 애매하게 붙어있던 위치)에서 "가공 무한" 버튼 바로 아래로 이동(`gather_panel.py`). 버튼 텍스트를 "🔁 가공 무한 시작 (강철괴/목재+/옷감+/가죽+)"로 변경
- 오프라인 시나리오 시뮬레이션(`run_cli`를 목으로 대체, 실제 게임 호출 없이 `_tick()` 직접 호출) 8가지 케이스로 검증: 전체 대기열 가득+버퍼 충분, 자유 슬롯+철괴 충분→강철괴, 자유 슬롯+철괴 버퍼 이하→철괴 보충 우선, 전체 가득+통나무 버퍼 이하→선제 채집, 가죽 원료 충분→가죽 가공, 가죽 재고<목표치+타닌가루 없음→계속 보충, 가죽 재고≥목표치+타닌가루 없음→막힘 보고, 완료작업 존재→회수 우선. 문법 검사 + 오프스크린 임포트/`GatherPanel` 생성 스모크 테스트 통과. 라이브 실행(정령의 날개 소모, 실제 게임 상태 변화)은 아직 미검증 — 사용자가 직접 앱에서 테스트 예정

## 2026-09-18 ("강철괴 무한" 알고리즘 개선 — 재료 버퍼 기반 선제 보충)

- 게임 서버 점검 종료 후 라이브 재검증: `complete_altering_work`(강철괴 7개 회수), `execute_altering`("철괴(광석)" 등록) 정상 동작 확인. `execute_gathering`("광석")은 `blocked`/`unknown_modal` 발생 — 화면에 알 수 없는 모달이 떠 있던 것으로 추정, 안전장치대로 자동 우회 없이 즉시 정지 확인
- 사용자가 실측으로 확인해준 정확한 레시피 소모량(철괴 3개+석탄 4개 → 강철괴 3개, 광석 20개 또는 철 광석 10개 → 철괴 3개)이 `steel_routine.py`에 이미 정확히 반영돼 있던 것 재확인
- **알고리즘 교체**: "대기열 안 놀리기"를 최우선으로, 사용자가 정의한 버퍼 규칙(채집 가능한 원자재 철 광석/광석/석탄은 항상 "7작업분(1배)"의 2배를 유지, 1배 이하로 떨어지면 채집)을 적용
  - 채집 원정은 실측 약 2분이 걸리는 반면 강철괴 1작업은 5분 걸린다는 점을 이용해, 대기열이 꽉 찬 채로 돌아가는 동안(유휴 시간)에도 버퍼가 1배 이하인 원자재가 있으면 선제적으로 채집을 보내 슬롯이 실제로 비기 전에 재료를 미리 채워둠(`_pick_proactive_target` — 가장 목표치 대비 많이 모자란 항목부터, 동률이면 철 광석>석탄>광석 순)
  - 철괴는 채집 대상이 아니라 빈 슬롯에서 30초짜리 철괴 가공으로 보충하는 대상이므로 별도 취급: 철괴 보유량이 자기 버퍼(21개, 7작업분) 이하로 떨어지면 강철괴(5분)보다 철괴 보충(30초)을 우선해, 강철괴 연속 생산이 철괴 재고를 0까지 밀어붙여 이후 모든 슬롯이 30초 철괴 가공만 반복하는 비효율을 방지
  - 빈 슬롯이 있는데 강철괴도 철괴도 못 만드는 상황(원자재 완전 고갈)에서는 그 자리에서 바로 채집(반응형) — 철괴가 부족하면 철광석/광석 중 더 여유 있는 쪽, 철괴는 충분한데 석탄만 부족하면 석탄을 채집
- 문법 검사(`py_compile`) + 오프스크린 임포트 스모크 테스트 통과. 새 버퍼 상수 값 확인: 철괴 21/42, 석탄 28/56, 철광석 70/140, 광석 140/280 (7작업분 / 2배 목표치)

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
