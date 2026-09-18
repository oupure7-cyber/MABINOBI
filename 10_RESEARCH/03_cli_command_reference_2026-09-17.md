# CLI 명령어 전체 레퍼런스 (2026-09-17 기준)

> `MabinogiMobile_CLI.exe capabilities` 응답([02_cli_capabilities_raw.json](02_cli_capabilities_raw.json)) 전체 28개 명령을 정리한 문서. 각 명령을 호출하면 받을 수 있는 필드(entry)까지 전부 표로 정리했다.
> 조사/작성일: 2026-09-18. 파일명의 날짜(2026-09-17)는 넥슨 공식 AI 커넥터 가이드 기준일([81_GUIDE_MD](../81_GUIDE_MD/마비노기_모바일_AI_커넥터_가이드.md) 참고)과 맞춘 **명령 카탈로그의 유효 시점**이다. 마비노기 모바일이 패치되어 `capabilities` 응답이 바뀌면 이 문서도 다시 확인해서 새 날짜로 별도 파일을 만들 것 — 기존 파일은 그대로 두고 비교할 수 있게 남겨둔다.
> 동일 소스 조사 기록: [01_ai_connector_interface.md](01_ai_connector_interface.md)

---

## 1. 전체 명령어 요약 (28개)

| # | 명령어 | 분류 | 설명 | 정령의 날개 | 사용자 확인 |
|---|---|---|---|---|---|
| 1 | `capabilities` | 메타 | 사용 가능한 명령 목록 조회 | - | - |
| 2 | `get_current_environment` | 조회 | 현재 위치/날씨/시간 | - | - |
| 3 | `get_activity` | 조회 | 자동전투/이동/전투/연주/상호작용 등 현재 상태 | - | - |
| 4 | `get_my_info` | 조회 | 캐릭터 기본 정보/능력치/현재 상태 | - | - |
| 5 | `get_quests` | 조회 | 퀘스트 트래커 목록 | - | - |
| 6 | `get_currencies` | 조회 | 보유 재화 목록 | - | - |
| 7 | `get_near_npcs` | 조회 | 주변 대화 가능 NPC | - | - |
| 8 | `get_near_pcs` | 조회 | 주변 플레이어 | - | - |
| 9 | `get_inventory` | 조회 | 인벤토리 무게(현재/최대) | - | - |
| 10 | `get_music_scores` | 조회 | 보유 악보 목록 | - | - |
| 11 | `get_instruments` | 조회 | 보유 악기 목록 | - | - |
| 12 | `get_items` | 조회 | 보유 아이템(소모품류) 목록 | - | - |
| 13 | `get_social_actions` | 조회 | 행동(Behaviour)/표정(Facial) 목록 | - | - |
| 14 | `get_daily_missions` | 조회 | 일일 미션 진행도 | - | - |
| 15 | `get_weekly_missions` | 조회 | 주간 미션 진행도 | - | - |
| 16 | `get_gatherable_items` | 조회 | 채집 가능 항목 + 도구 보유 여부 | - | - |
| 17 | `get_alterable_items` | 조회 | 가공 레시피 + 재료 보유 여부 | - | - |
| 18 | `get_altering_works` | 조회 | 진행 중/완료된 가공 작업 | - | - |
| 19 | `get_craftable_items` | 조회 | 제작 레시피 + 재료 보유 여부 | - | - |
| 20 | `write_chat` | 실행 | 채팅 메시지 전송 (행동/표정 명령 포함) | - | ✅ `requiresConfirm` |
| 21 | `play_music_score` | 실행 | 악보 연주 시작 | - | - |
| 22 | `change_instrument` | 실행 | 악기 교체 | - | - |
| 23 | `stop_action` | 실행 | 진행 중 동작(연주/자동전투/채집 등) 정지 | - | - |
| 24 | `stand_up` | 실행 | 앉기 해제 | - | - |
| 25 | `execute_gathering` | 실행 | 목표 수량까지 채집 / 자동낚시 시작 | **5** | - (실행 중 `blocked` 가능) |
| 26 | `execute_altering` | 실행 | 가공 작업 큐 등록 (시설 이동 포함) | **5** | - (실행 중 `blocked` 가능) |
| 27 | `complete_altering_work` | 실행 | 완료된 가공 결과 수령 (시설 이동 포함) | - | - (실행 중 `blocked` 가능) |
| 28 | `execute_crafting` | 실행 | 레시피 제작 (시설 이동 + 결과 수령 포함) | **5** | - (실행 중 `blocked` 가능) |

- **정령의 날개**: 표시된 3개 명령만 실행당 5개 소모. 부족하면 `not_enough_currency`로 거부.
- **사용자 확인**: `write_chat`만 CLI 메타데이터에 `requiresConfirm: true`가 명시됨(게임 내 채팅 승인 팝업과 대응). `execute_*` 계열은 별도의 확인 팝업 대신, 실행 중 사용자 입력이 필요한 UI를 만나면 `blocked` + `kind`를 반환하고 즉시 멈추는 방식으로 안전장치가 걸려 있다(자동 클릭 없음).
- 거래소/캐시샵/길드운영/1:1메시지/외부연동/자동성장 관련 명령은 이 28개 안에 **존재하지 않는다** ([00_SPEC/02_scope_boundaries.md](../00_SPEC/02_scope_boundaries.md)와 일치).

---

## 2. 조회형 명령 상세 (18개) — 얻을 수 있는 entry 전체

### `get_current_environment`
입력 없음.

| 필드 | 설명 |
|---|---|
| `ChannelDisplayName` | 현재 채널 이름 |
| `GameSpaceDisplayName` | 현재 지역/맵 이름 |
| `WorldPosition` | 월드 좌표 |
| `Weather` | 현재 날씨 |
| `ErinnNow` | 에린 시각(게임 내 시간) |
| `Housing.IsInHousing` | 마이홈 안에 있는지 |
| `Housing.IsOwnedHousing` | 본인 소유 마이홈인지 |
| `Housing.CanEnterHousing` | 지금 본인 마이홈에 들어갈 수 있는지 |
| `Housing.CannotEnterHousingReason` | 못 들어가는 이유(있을 때) |
| `Housing.CanExitHousing` | 현재 마이홈에서 나갈 수 있는지 |

### `get_activity`
입력 없음. 자동전투/이동/전투/대화/던전/연주/상호작용/모드 상태를 묶어서 반환.

| 그룹 | 필드 | 설명 |
|---|---|---|
| `autoPlay` | `IsAutoPlaying`, `CanStartAutoPlay`, `AutoPlayTarget`, `AutoPlayTargetDisplayName` | `AutoPlayTarget`: none/quest/goddess_mission/shortcut/division_objective/recommended_activity/guide_mission. **CLI로 자동전투를 시작시키는 명령은 없음(조회만 가능)** |
| `autoTravel` | `IsAutoTraveling`, `AutoTravelRemainingPositionCount` | 자동 이동 중 여부/남은 경유지 수 |
| `combatState` | `IsDead`, `IsReviving`, `IsInCombat` | 사망/부활/전투 중 여부 |
| `dialogue` | `IsDialoguePlaying`, `IsDialogueNextAvailable`, `IsWaitingForSelection` | 대화 진행 상태 |
| `Dungeon` | `State`, `IsBossBattleInProgress` | `State`: NotInDungeon/Entering/InProgress/Cleared |
| `Battlefield` | `IsInBattleField` | 전장 여부 |
| `Tutorial` | `IsPlaying` | 튜토리얼 진행 여부 |
| `Scenario` | `IsInScenario`, `IsSequencePlaying` | 시나리오 진행 여부 |
| `Performance` | `IsPlaying`, `InstrumentName`, `MusicTitle`, `IsCopyingAllowed`, `IsLoop`, `StartAt`, `TotalDurationSeconds`, `ElapsedSeconds`, `RemainingSeconds`, `ChannelCount` | 현재 연주 상태 |
| `Interaction` | `HasTarget`, `IsTargetAttackable`, `AvailableInteractionType`, `LastRunningInteractionType`, `TargetKind` | 상호작용 가능 대상 (`TargetKind`: DungeonEntrance/Elevator/Fountain/CutscenePlayProp/Gimmick/Prop/Actor/None) |
| `Mode` | `MainButtonState`, `MountPartState`, `SitState`, `IsPlayingMiniGame`, `IsHousingEditMode` | `MainButtonState`: Hide/Stop/Combat/Interaction/Compass/ScenarioQTE/Fishing/FishingPull/Housing |

### `get_my_info`
입력 없음. 모든 능력치 필드는 `{DisplayName, Value}` 형태.

| 필드 | 설명 |
|---|---|
| `Title` | 칭호 |
| `RealmName` | **서버(월드) 이름** — 캐릭터 이름 아님. CLI는 어떤 명령에서도 캐릭터 실명을 노출하지 않음 |
| `Level` | 레벨 |
| `EnabledCombatJobDisplayName` | 현재 전투 직업 |
| `CombatScore` / `LivingScore` / `AttractivenessScore` / `DecorScore` | 전투력/생활력/매력/데코 점수 |
| `HealthMax` / `AttackPower` / `DefencePower` / `ArcaneResistance` | 최대 체력/공격력/방어력/마도 저항 |
| `STR` / `DEX` / `INT` / `LUCK` / `WILL` | 힘/솜씨/지력/행운/의지 |
| `PaladinStats.*` | 전사 계열 스탯(신성력/항마력/정의/심판/질서/가호) — 직업에 따라 다른 그룹이 나올 수 있음 |
| `Vitals.HealthCurrent` / `HealthMax` | 현재/최대 체력 |
| `Vitals.ShieldAmount` / `ShieldMax` | 보호막 |
| `Vitals.SatietyValue` / `SatietyMax` / `SatietyRatio` | 포만감 |
| `Vitals.InventoryWeightCurrent` / `InventoryWeightMax` | 인벤토리 무게 |
| `Vitals.ActiveBuffCount` | 활성 버프 수 |

### `get_quests`
입력 없음. 현재 보이는 퀘스트 트래커 항목만 반환(배열).

| 필드 | 설명 |
|---|---|
| `QuestTitle` | 퀘스트 제목 |
| `Source` | main/pinned_sub/auto_register_sub/auto_register_candidate_sub/event/goddess_mission/shortcut/division_objective/guide_mission/recommended_activity |
| `SourceDisplayName` | `Source`의 표시 이름 (있으면 이걸 그대로 사용) |
| `Objectives[].Description` | 목표 설명 |
| `Objectives[].IsCompleted` | 완료 여부 |
| `Objectives[].Count` / `Goal` | 진행 수치 / 목표 수치 |

### `get_currencies`
입력 없음. 배열.

| 필드 | 설명 |
|---|---|
| `DisplayName` | 재화 이름 (골드/정령의 날개/데카 등 28종) |
| `Amount` | 보유 수량 |

### `get_near_npcs`
입력 없음. 반경 30, 대화 가능 NPC(및 NPC 동료)만.

| 필드 | 설명 |
|---|---|
| `Name` | NPC 코드명 |
| `Title` | 칭호 |
| `DisplayName` | 표시 이름 |
| `Distance` | 거리 |

### `get_near_pcs`
입력 없음. 반경 30. 다른 플레이어의 실명은 노출 안 됨(`RealmName`=서버명만).

| 필드 | 설명 |
|---|---|
| `RealmName` | 서버 이름 (실명 아님) |
| `Title` | 칭호 |
| `Distance` | 거리 |
| `ClothesCount` / `CrowdAppearanceColorCount` | 착용 의상 수 / 외형 색상 수 |
| `IsRobeWeared` / `IsHoodOn` / `IsWeaponHidden` | 로브/후드/무기숨김 여부 |
| `Level` / `EnabledCombatJobDisplayName` | 레벨 / 직업 |
| `CombatScore` / `LivingScore` / `AttractivenessScore` | 각종 점수 |
| `IsFriend` / `IsInParty` / `HasGuild` / `IsSameGuild` / `IsCoOwner` | 친구/파티/길드 여부 (`IsCoOwner`는 마이홈 공동 소유자 여부, 마이홈 밖에선 항상 false) |
| `IsInCombat` | 전투 중 여부 |
| `Performance.*` | 연주 중이면 악보 제목/루프/재생 경과 등 |

### `get_inventory`
입력 없음.

| 필드 | 설명 |
|---|---|
| `CurrentInventoryWeight` / `CurrentInventoryWeightAsDecimal` | 현재 인벤토리 무게 |
| `MaxInventoryWeight` / `MaxInventoryWeightAsDecimal` | 최대 인벤토리 무게 |

### `get_music_scores`
입력(선택): 제목 부분 문자열(대소문자 무관). 배열.

| 필드 | 설명 |
|---|---|
| `Location` | inventory / account_storage / character_storage |
| `DisplayTitle` | 악보 제목 (`play_music_score`에 그대로 전달) |
| `IsCopyingAllowed` | 복사 허용 여부 |
| `IsLocked` | 잠금 여부 |

### `get_instruments`
입력(선택): 이름 부분 문자열. 배열.

| 필드 | 설명 |
|---|---|
| `Name` | 악기 이름 (`change_instrument`에 그대로 전달) |
| `Durability` | 내구도 |
| `IsEquipped` | 현재 장착 여부 |

### `get_items`
입력(선택): `{"category": "...", "name": "..."}` 둘 다 부분 문자열 필터. 소모품류만(장비/코스튬/펫 제외). 배열.

| 필드 | 설명 |
|---|---|
| `DisplayName` | 아이템 이름 |
| `Category` / `CategoryDisplayName` | 카테고리 코드 / 표시 이름 (예: Food, Ingredient, Consumable, Consumable_Box, Consumable_Growth, Quest) |
| `Count` | 보유 수량 |
| `Location` | inventory / account_storage / character_storage |
| `IsLocked` | 잠금 여부 |

### `get_social_actions`
입력(선택): 이름/명령어 부분 문자열.

| 그룹 | 필드 | 설명 |
|---|---|---|
| `Behaviours[]` | `DisplayName`, `ChatCommands[]` | 행동. `ChatCommands`를 `write_chat`으로 보내면 실행됨(표시 이름이 아닌 `ChatCommands` 값 그대로 써야 함) |
| `Facials[]` | `DisplayName`, `EmojiText` | 표정. `EmojiText`를 `write_chat`으로 보내면 실행됨 |

### `get_daily_missions` / `get_weekly_missions`
입력 없음. 배열.

| 필드 | 설명 |
|---|---|
| `Title` / `Description` | 미션 제목 / 설명 |
| `CurrentCount` / `GoalCount` | 진행 수치 / 목표 수치 |
| `IsCompleted` | 완료 여부 |
| `IsRewardReceived` | 보상 수령 여부 |
| `HasShortcut` | 자동이동 숏컷 지원 여부 |

### `get_gatherable_items`
입력(선택): 이름 부분 문자열. 생활 스킬 레벨 조건을 충족한 항목만 표시(잠긴 항목은 안 보임).

| 필드 | 설명 |
|---|---|
| `DisplayName` | 채집 항목 이름 (`execute_gathering`에 그대로 전달) |
| `ToolOk` | 필요 도구 보유 및 내구도 여부 (false면 도구 없음/내구도 0) |

### `get_alterable_items`
입력(선택): 레시피명 또는 재료명 부분 문자열. 제작(`get_craftable_items`)과 별개 — 추출물/포자/가루/실/목재 등.

| 필드 | 설명 |
|---|---|
| `DisplayName` | 가공 레시피 이름 (`execute_altering`에 그대로 전달) |
| `Alterable` | 지금 가공 가능한지 |
| `ProducedPerWork` | 작업 1회당 생산량 |
| `Reason` | 불가 사유: insufficient_facility_level / not_enough_ingredient / ingredient_locked / insufficient_transfer_cost |
| `MissingIngredients[].DisplayName` / `Required` / `Owned` | 부족한 재료 이름 / 필요량 / 보유량 |

### `get_altering_works`
입력 없음. 모든 시설의 가공 큐 상태.

| 필드 | 설명 |
|---|---|
| `completedCount` | 수령 대기 중인 작업 수 |
| `works[].DisplayName` | 작업 이름 |
| `works[].FacilityName` | 시설 이름 (같은 시설 작업은 `complete_altering_work` 한 번에 같이 수령됨) |
| `works[].State` | NotStarted / InProgress / Completed |
| `works[].IsCompleted` | 완료 여부 |
| `works[].RemainingSeconds` | 남은 시간(완료 시 0) |

### `get_craftable_items`
입력(선택): 레시피명 또는 재료명 부분 문자열.

| 필드 | 설명 |
|---|---|
| `craftingUnlocked` | 제작 시스템 해금 여부 (false면 `items`는 빈 배열) |
| `DisplayName` | 레시피 이름 (`execute_crafting`에 그대로 전달) |
| `Craftable` | 지금 제작 가능한지 |
| `ProducedPerCraft` | 제작 1회(`craftCount=1`)당 생산량 |
| `Reason` | 불가 사유: insufficient_living_skill_level / insufficient_facility_level / insufficient_decor_score / not_enough_ingredient / ingredient_locked / insufficient_transfer_cost |
| `MissingIngredients[].DisplayName` / `Required` / `Owned` | 부족한 재료 이름 / 필요량 / 보유량 |

---

## 3. 실행형 명령 상세 (9개) — 입력 / 성공 / 실패

### `write_chat`
- **입력**: 원문 문자열(JSON 아님), 최대 50자. 일반 채팅, `get_social_actions`의 `ChatCommands`(행동), 또는 `EmojiText`(표정) 중 하나.
- **성공**: `accepted`
- **실패**: `invalid_body`(글자수 초과 등) / `rejected` + `unsupported_command`(예약 명령 `/지역`, `/파티`, 긴급탈출, `#암호` 등) / `rejected` + `rate_limited`(`retryAfterSeconds` 이후 재시도)
- **안전장치**: `requiresConfirm: true` — 게임 내 승인 없이는 전송되지 않음.

### `play_music_score`
- **입력**: `{"title": "<get_music_scores의 DisplayTitle>"}`
- **성공**: `accepted`
- **실패**: `invalid_body`(title 누락) / `rejected` — `not_found`, `no_instrument`(먼저 `change_instrument` 필요), `not_available_on_combat`, `not_available_on_riding`, `not_available_on_dead`, `system_error`

### `change_instrument`
- **입력**: `{"name": "<get_instruments의 Name>"}`
- **성공**: `accepted` (이미 장착 중인 악기를 요청해도 accepted)
- **실패**: `invalid_body`(name 누락) / `rejected` — `not_found`, `is_playing_instrument`, `not_available_on_dead`, `level_requirement`, `invalid_target`, `failed_unequip`, `system_error`

### `stop_action`
- **입력**: 없음
- **성공**: `accepted` — 연주/자동전투/운반/채집 등 정지 가능한 동작을 멈춤
- **실패**: `rejected` — `invalid_state`(멈출 동작 없음), `timeout`
- **비고**: 앉기(/앉기)는 이 명령으로 안 풀림 → `stand_up` 사용

### `stand_up`
- **입력**: 없음
- **성공**: `accepted`
- **실패**: `rejected` — `not_sitting`, `no_control_object`, `timeout`(앉은 직후엔 잠시 후 재시도)

### `execute_gathering` ⚠️ 정령의 날개 5 소모
- **입력**: `{"displayName": "<get_gatherable_items의 DisplayName>"}`
- **성공**: 채집형 — `accepted` + `result: completed`(`gained`, `target`) / 낚시형 — `accepted` + `result: started`(목표 없음, `stop_action`으로 종료)
- **중간 종료**: `accepted` + `result: stopped`(`gained`, `target`, `message`)
- **중단(에러)**: `error: blocked`(`kind` 포함, 사용자가 직접 해결해야 함) / `overweight` / `timeout` / `canceled` / `tool_broken`
- **시작 전 거부**: `rejected` — `not_found`, `no_route`, `insufficient_living_skill_level`, `overweight`, `tool_missing`, `tool_broken`, `required_consumable_missing`, `not_in_field`, `blocked`
- **비고**: 1회 호출당 최대 100개까지, 그 이상은 재호출. 부족 시 `not_enough_currency` / 결제 실패 시 `cost_payment_failed`.

### `execute_altering` ⚠️ 정령의 날개 5 소모
- **입력**: `{"displayName": "<get_alterable_items의 DisplayName>"}`
- **성공**: `accepted` + `result: started` (시설 이동 포함, 큐 등록까지만 — 즉시 완성 아님)
- **실패**: `blocked`(`kind` 포함) / `component_not_found` / `facility_not_found` / `timeout` / `canceled` / `result: stopped_by_user`(도착 전 사용자가 이동 중단) — 시작 전 거부: `not_found`, `not_available`, `requires_user_interaction`(게임 내에서 직접 시작해야 함), `insufficient_facility_level`, `not_enough_ingredient`, `ingredient_locked`, `insufficient_transfer_cost`, `overweight`, `not_in_field`, `facility_not_found`
- **비고**: 진행 상황은 `get_altering_works`, 수령은 `complete_altering_work`. N개 큐에 넣으려면 완료될 때마다 재호출.

### `complete_altering_work`
- **입력**: `{"displayName": "<get_altering_works의 DisplayName>"}`
- **성공**: `accepted` + `{collected, rewards, criticalRewards, message}` — 해당 아이템이 만들어지는 시설의 **완료된 작업 전부**를 한 번에 수령(시설 이동 포함)
- **실패**: `timeout`(수령 미확인, `get_altering_works`로 재확인) / `blocked` / `canceled` / `result: stopped_by_user` — 시작 전 거부: `no_altering`, `no_completed_work`, `not_found`, `no_completed_work_at_facility`, `not_completed_yet`(해당 아이템 자체가 아직 진행 중), `blocked`, `overweight`, `not_in_field`, `facility_not_found`

### `execute_crafting` ⚠️ 정령의 날개 5 소모
- **입력**: `{"displayName": "<get_craftable_items의 DisplayName>", "craftCount": 1}` — `craftCount`는 **제작 횟수**(생산 아이템 수 아님). 기본값 1, 시설별 상한 있음(초과 시 `invalid_count` + `maxCount`)
- **성공**: `accepted` + `result: completed`(`craftCount`, `rewards`, `criticalRewards`) 또는 `result: stopped_by_user`(완료 전 사용자가 중단, 생산 없음)
- **실패**: `blocked`(`kind`) / `timeout` / `canceled` — 시작 전 거부: `crafting_locked`, `not_found`, `not_available`, `invalid_count`(+`maxCount`), `insufficient_living_skill_level`, `insufficient_facility_level`, `insufficient_decor_score`, `not_enough_ingredient`, `ingredient_locked`, `insufficient_transfer_cost`, `overweight`, `not_in_field`, `facility_not_found`
- **비고**: 시설 이동 + 제작 + 결과 수령까지 한 호출에서 처리, UI 자동으로 닫힘.

---

## 4. 공통 패턴 정리

- **정령의 날개 소모 3형제**: `execute_gathering` / `execute_altering` / `execute_crafting`만 실행당 5개 소모. 부족 시 `not_enough_currency`, 결제 실패 시 `cost_payment_failed`. 성공 응답에 `cost`와 잔액 문구 포함.
- **`blocked` + `kind` 패턴**: 실행형 명령(특히 채집/가공/제작) 도중 사용자 입력이 필요한 UI가 뜨면 그 자리에서 멈추고 `blocked`와 `kind`(해결해야 할 대상)를 반환. **자동으로 클릭해서 넘기면 안 되고, 사용자에게 그대로 안내 후 대기**해야 함.
- **DisplayName 체이닝**: 대부분의 실행형 명령은 대응하는 조회형 명령이 반환한 `DisplayName`을 **정확히 그대로** 입력받는 구조 (`get_gatherable_items` → `execute_gathering`, `get_alterable_items` → `execute_altering`, `get_altering_works` → `complete_altering_work`, `get_craftable_items` → `execute_crafting`, `get_music_scores` → `play_music_score`, `get_instruments` → `change_instrument`).
- **본인 캐릭터 이름 비노출**: `get_my_info`/`get_near_pcs` 모두 실명 필드가 없고 `RealmName`(서버)·`Title`(칭호)만 제공 — 공식 정책("다른 모험가 정보 미전달")이 본인에게도 동일 적용.
- **자동성장 관련 명령 없음**: `get_activity`로 자동전투 상태 조회는 가능하나, 이를 시작시키는 명령 자체가 28개 안에 없음 — 정책과 인터페이스가 일치.
