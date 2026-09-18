# AI 커넥터 인터페이스 조사

> 2026-09-18, 실행 중인 게임 클라이언트(PID는 실행마다 바뀜, 조사 당시 12920)에 대해 CLI를 직접 실행해서 확인함.

## 실행 파일

| 파일 | 경로 | 용도 |
|---|---|---|
| `MabinogiMobile.exe` | `C:\Nexon\MabinogiMobile\MabinogiMobile.exe` | 게임 클라이언트 본체 (Unity, ProductVersion `2021.3.51p3` — Unity 엔진 버전 표기, 게임 자체 버전 아님) |
| `MabinogiMobile_CLI.exe` | `C:\Nexon\MabinogiMobile\MabinogiMobile_CLI.exe` | AI 커넥터용 CLI. FileDescription "MabinogiMobile_CLI", CompanyName "Devcat"(마비노기 개발사), 버전 `0.1.0+a62d48bb...` |

기타 참고: `C:\Nexon\MabinogiMobile\BlackCipher\` 에 `NGService.exe`/`NGService64.exe` — 넥슨 안티치트(BlackCipher) 관련 프로세스로 추정. **PowerShell `Get-Process`/.NET API로는 `MabinogiMobile.exe`가 조회되지 않고, `tasklist`(레거시 API)로만 보임** — 안티치트가 일반 프로세스 열거 API로부터 프로세스를 숨기는 것으로 보임. → 자동화 프로그램에서 "게임이 켜져 있는가"를 판단할 때 `Get-Process`에 의존하면 안 되고 `tasklist` 또는 CLI의 `status` 명령을 써야 한다.

## PID는 실행마다 바뀌는가?

**예, 매번 바뀐다.** PID는 OS가 프로세스를 생성할 때 그 순간에 할당하는 값이라, 재실행하면 이전 PID가 이미 다른 프로세스에 재사용됐을 수도 있고 사실상 예측 불가능하다. 자동화 설계 시 PID를 하드코딩하지 말고, 매번 프로세스 이름으로 조회하거나 (`MabinogiMobile_CLI.exe status`로 파이프 연결 여부 확인) 동적으로 확인해야 한다.

## CLI 사용법

```
MabinogiMobile_CLI.exe --help
MabinogiMobile_CLI.exe status
MabinogiMobile_CLI.exe capabilities
MabinogiMobile_CLI.exe <dispatch-command> [body]
```

- 한 번 호출에 한 명령을 실행하고 JSON을 stdout으로 반환한 뒤 종료하는 **1회성(one-shot) CLI**. 상시 실행되는 MCP 서버 프로세스가 아니라, 실행 중인 게임 클라이언트와 **named pipe로 통신**하는 얇은 클라이언트로 보인다 (`status` → `{"pipe":"connected"}`).
- 실제 테스트: `MabinogiMobile_CLI.exe get_current_environment` → 정상적으로 현재 위치/날씨/시간 JSON 반환 확인.
- 전체 명령 스키마는 `capabilities` 명령으로 그대로 얻을 수 있음 → 원본 저장: [02_cli_capabilities_raw.json](02_cli_capabilities_raw.json)

## 명령 목록 (총 28개, capabilities 응답 기준)

### 조회형 (정령의 날개 미소모)
| 명령 | 설명 |
|---|---|
| `capabilities` | 명령 목록 조회 (`loading: true`면 아직 카탈로그 준비 안 됨 — 유저가 게임에 들어간 후 재조회) |
| `get_current_environment` | 위치/날씨/시간(에린 시각)/하우징 상태 |
| `get_activity` | 자동전투 이동, 전투, 대화, 던전, 연주, 상호작용 등 현재 상태 |
| `get_my_info` | 캐릭터 스탯/HP/포만감/인벤토리 무게 등 |
| `get_quests` | 퀘스트 트래커 목록 |
| `get_currencies` | 재화 목록 |
| `get_near_npcs` / `get_near_pcs` | 주변 NPC/플레이어 (반경 30) |
| `get_inventory` | 인벤토리 무게 |
| `get_items` | 소지 아이템(소모품/재료 등) 목록, category/name 필터 |
| `get_music_scores` / `get_instruments` | 보유 악보/악기 목록 |
| `get_social_actions` | 사용 가능한 행동(Behaviour)/표정(Facial) 목록 |
| `get_daily_missions` / `get_weekly_missions` | 일일/주간 미션 진행도 |
| `get_gatherable_items` | 채집 가능한 항목 목록(도구 보유 여부 포함) |
| `get_alterable_items` / `get_altering_works` | 가공 레시피 / 진행 중인 가공 작업 |
| `get_craftable_items` | 제작 레시피 |

### 실행형
| 명령 | 설명 | 비용 | 확인 필요 |
|---|---|---|---|
| `write_chat` | 채팅 전송 (최대 50자, 원문 문자열) | 없음 | ✅ `requiresConfirm: true` — 게임 정책과 일치 |
| `execute_gathering` | 지정 항목 목표 수량까지 채집 / 낚시는 자동낚시 시작 | **정령의 날개 5개** | 소모성 작업이라 확인 팝업 가능 |
| `execute_crafting` | 지정 레시피 제작 (`craftCount`로 횟수 지정) | **정령의 날개 5개** | 〃 |
| `execute_altering` | 지정 가공 레시피 큐 등록 | **정령의 날개 5개** | 〃 |
| `complete_altering_work` | 완료된 가공 결과 수령 | 명시 없음 | - |
| `play_music_score` | 보유 악보 연주 | 명시 없음(공식 가이드의 "연주"는 정령의 날개 소모 대상으로 안내됨 — **불일치 가능성, 실사용 시 재확인 필요**) | - |
| `change_instrument` | 악기 교체 | 없음 | - |
| `stop_action` / `stand_up` | 진행 중 동작 정지 / 앉기 해제 | 없음 | - |

## 눈에 띄는 설계 특징 (자동화 설계에 직접 영향)

1. **화이트리스트가 인터페이스 자체에 이미 내재**: 거래소, 캐시샵/결제, 길드 운영, 1:1 메시지, 외부 연동에 대응하는 명령이 **CLI에 전혀 존재하지 않음**. `00_SPEC/02_scope_boundaries.md`의 금지 목록이 정책 차원이 아니라 인터페이스 차원에서도 막혀 있음을 확인.
2. **"성장과 관련된 자동 플레이"도 명령으로 노출되지 않음**: `get_activity`가 `autoPlay.IsAutoPlaying` / `AutoPlayTarget`(quest, goddess_mission 등) 상태를 **조회는 가능**하지만, 이를 시작시키는 `start_autoplay` 류 명령이 캐퍼빌리티 목록에 없음. 즉 CLI로는 자동전투/자동성장을 켤 수 없고 상태 확인만 가능 — 공식 금지 정책과 일치.
3. **`write_chat`은 일반 채팅 대신 행동(Behaviour)/표정(Facial) 명령도 처리**: `get_social_actions`로 조회한 `ChatCommands`(예: `/전통댄스`)나 `EmojiText`를 그대로 `write_chat`에 보내면 행동/표정으로 실행됨. 단, 이동/긴급탈출/패스코드 등 예약 명령(`/지역`, `/파티`, `#...`)은 `unsupported_command`로 거부.
4. **`write_chat`에 레이트리밋 존재**: `rejected` + `error: rate_limited` + `retryAfterSeconds` 반환. 자동화 설계 시 이 값을 그대로 대기 시간으로 써야 함(도배 방지, 운영정책 위반 회피).
5. **소모성 작업 공통 실패 패턴**: `execute_gathering`/`execute_crafting`/`execute_altering` 모두 실행 중 사용자 입력이 필요한 UI가 뜨면 `blocked` + `kind`(해결해야 할 UI/상태)를 반환하고 동작을 멈춤 — **자동으로 클릭해서 넘기지 말고, `kind`를 사용자에게 그대로 안내하고 대기**해야 함 (00_SPEC의 안전장치 요구사항과 정확히 대응).
6. **`not_enough_currency` / `cost_payment_failed`**: 정령의 날개가 부족하거나 결제 실패 시 명확한 에러 코드로 거부됨 — 자동화 쪽에서 사전에 잔량을 `get_currencies`로 확인하고 예산 체크를 구현할 수 있음.
7. **`execute_gathering`/`execute_crafting`은 한 번에 상한이 있음**: 채집은 호출당 최대 100개, 제작은 시설별 `maxCount` 존재(`invalid_count` 에러에 포함) → 대량 작업은 반복 호출로 나눠야 함.

## Claude Code MCP 자동 등록 여부 (미확인/열린 질문)

- `~/.claude.json`을 확인한 결과, 현재 이 프로젝트나 전역 설정에 Mabinogi 관련 `mcpServers` 항목은 **없음**. 즉 지금 시점에는 Claude Code가 이 CLI를 MCP 서버로 자동 인식하고 있지 않다.
- CLI 자체는 1회성 호출-응답 구조라, Claude Code가 이걸 직접 MCP stdio 서버로 등록하기보다는 **별도의 MCP 래퍼(넥슨 제공 또는 각 AI 도구 확장)가 내부적으로 이 CLI를 호출**하는 구조일 가능성이 높다.
- ⬜ 다음에 확인할 것: 게임 내 `[환경설정] → [게임] → [AI 제어]`를 껐다가 다시 켜는 시점에 Claude Code 설정(`.claude.json` 또는 프로젝트별 `.mcp.json`)에 변화가 생기는지, 혹은 넥슨이 별도 설치 단계(확장 프로그램 등)를 요구하는지.

## `get_my_info` 필드 노트 (사용자 확인으로 확정)

- `RealmName`(예: "칼릭스")은 **서버(월드) 이름**. 캐릭터 이름이 아님 — 사용자 본인이 직접 확인.
- **CLI/AI 커넥터는 캐릭터의 실제 이름(닉네임)을 어떤 명령에서도 노출하지 않는다.** `get_my_info`에는 `Title`(칭호)과 `RealmName`(서버)만 있고 이름 필드 자체가 없음. 이건 공식 가이드의 "다른 모험가님의 정보는 전달되지 않습니다 (예: 캐릭터 이름)" 정책이 **타인뿐 아니라 본인 캐릭터 이름 조회에도 동일하게 적용**된다는 뜻으로 해석됨.
- `get_near_pcs` 역시 같은 `RealmName`(서버)/`Title`(칭호) 필드만 쓰므로, 다른 플레이어의 실제 이름도 노출되지 않음 — 정책과 실제 동작이 일치함 (앞서 제기했던 상충 우려는 해소됨).
- **자동화 설계 영향**: 캐릭터 이름으로 로그를 남기거나 사용자에게 "내 캐릭터"를 구분해서 보여줘야 하는 기능은 이 API로는 만들 수 없음. 필요하면 사용자가 직접 입력한 값을 별도로 관리해야 함.

## 남은 조사 항목

- [x] AI 제어 옵션을 켠 후 Claude Code에 MCP 서버가 자동 등록되는가 → **현재 미등록으로 확인, 등록 트리거 조건 추가 조사 필요**
- [x] 각 툴의 파라미터/응답 스키마 → **`capabilities` 응답으로 전부 확보** ([02_cli_capabilities_raw.json](02_cli_capabilities_raw.json))
- [x] 정령의 날개 소모 확인 방식 → 실행형 명령 응답에 `cost`와 잔액 문구 포함, 부족 시 `not_enough_currency`
- [x] 1시간 연속 실행 팝업 감지 → 아직 실제로 트리거해서 확인 못 함 (`blocked`/`kind` 패턴에 포함될 것으로 추정, 실사용 중 재확인 필요)
- [ ] 채팅 승인 팝업이 CLI 응답에 어떻게 반영되는지 (accepted가 승인 완료 의미인지, 아니면 게임 쪽 팝업이 별도로 뜨는지) — 실제 `write_chat` 호출 테스트 필요 (부작용 있는 명령이라 사용자 확인 후 진행)
- [ ] `play_music_score`의 정령의 날개 소모 여부 불일치 — 실제 연주 실행해서 확인 필요
- [ ] 게임 재시작 시 CLI가 다시 연결되는 데 걸리는 시간/재시도 로직 필요 여부
