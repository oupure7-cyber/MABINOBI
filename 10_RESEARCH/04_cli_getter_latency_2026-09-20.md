# CLI getter 호출 latency 실측 (2026-09-20)

`MabinogiMobile_CLI.exe`의 getter성 명령 19개(캡슐화된 상태 변경 없는 조회 전용 — `execute_*`/`write_*`/`play_*`/`change_instrument`/`stop_action`/`stand_up`/`complete_altering_work` 제외) 각각을 게임이 연결된 상태에서 20회씩 **순차(sync)** 호출해 측정한 결과. 오버레이(`app/dashboard/overlay.py`)나 캐릭터 감지(`character_watcher.py`)처럼 주기적으로 폴링하는 기능의 refresh 주기를 정할 때 이 표를 기준으로 삼을 것.

## 왜 병렬화가 안 되는가

`cli_client.py`는 명령 하나당 `MabinogiMobile_CLI.exe`를 매번 새 서브프로세스로 띄우는 구조이고, 두 호출을 동시에 실행하면 둘 다 깨지는 것을 예전에 실측으로 확인해서 전역 `threading.Lock`(`_CLI_LOCK`)으로 강제 직렬화해뒀다(`run_cli`는 블로킹, `try_run_cli`는 바쁘면 즉시 `None`). 즉 이 앱에서 CLI를 부르는 모든 곳(JOB 워커, 캐릭터 감지 폴링, 오버레이 폴링)은 실질적으로 같은 큐를 나눠 쓰는 셈이라, 폴링 주기를 짧게 잡을수록 "내 차례가 안 와서 이번 틱은 스킵됨"이 잦아진다.

## 측정값 (N=20, sync, 오름차순)

| 명령 | 평균(ms) | 최소 | 최대 |
|---|---:|---:|---:|
| get_near_npcs | 104.9 | 95.2 | 125.7 |
| get_inventory | 107.6 | 93.6 | 119.6 |
| get_activity | 108.9 | 94.8 | 160.7 |
| get_currencies | 110.9 | 99.1 | 157.8 |
| get_alterable_items | 111.1 | 98.2 | 157.9 |
| get_current_environment | 113.1 | 95.4 | 172.7 |
| get_altering_works | 114.0 | 93.1 | 163.6 |
| get_my_info | 116.1 | 94.6 | 167.5 |
| get_near_pcs | 112.9 | 95.0 | 165.9 |
| get_quests | 119.4 | 95.4 | 217.8 |
| get_weekly_missions | 119.2 | 110.9 | 175.1 |
| capabilities | 122.2 | 96.9 | 187.3 |
| get_instruments | 129.5 | 110.6 | 175.9 |
| get_items | 137.5 | 112.1 | 243.6 |
| get_social_actions | 138.1 | 110.1 | 236.1 |
| get_daily_missions | 139.0 | 108.8 | 210.3 |
| get_gatherable_items | 136.5 | 113.2 | 237.9 |
| get_music_scores | 141.5 | 87.3 | 254.5 |
| get_craftable_items | 165.5 | 124.1 | 230.0 |

- **전체 평균: 약 123.6ms/call** (19종 × 20회 = 380 호출, 총 벽시계 47초)
- 실측 최저치: `get_music_scores` 87.3ms / 최고치: `get_craftable_items` 평균 165.5ms(레시피 전체 스캔 때문으로 추정)
- 매 호출이 서브프로세스 기동을 포함하므로, 이 100~165ms는 IPC 자체보다 프로세스 spawn 오버헤드가 지배적일 가능성이 높다. 즉 이 값이 사실상 "이 CLI로 낼 수 있는 최저 latency"다.

## 폴링 주기 설계에 주는 시사점

- 오버레이는 매 틱마다 `get_altering_works` + `get_current_environment` 2개를 부른다 → 두 호출만으로도 순수 latency 합이 약 227ms. 현재 `TRACK_INTERVAL_MS = 500`(오버레이)과 `POLL_INTERVAL_MS = 2000`(캐릭터 감지)이 이 큐를 나눠 쓰는데, 오버레이 쪽은 `try_run_cli`(논블로킹)라서 바쁘면 그냥 스킵하고 다음 틱까지 값이 갱신되지 않는다 — 사용자가 "refresh가 안 되는 것 같다"고 느끼는 원인일 가능성이 높음(아래 known-issue 참고).
- 500ms 주기에 227ms+가 이미 깔려 있으면 유휴 시간이 넉넉하지 않아, 다른 폴링(캐릭터 감지)과 겹치는 순간마다 스킵될 여지가 크다. 필요하면 오버레이 주기를 늘리거나(예: 1000ms), 한 틱에 두 패널을 몰아 부르지 말고 번갈아 하나씩만 부르는 식으로 나누는 것을 고려.
