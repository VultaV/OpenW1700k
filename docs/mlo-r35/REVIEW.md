# r35 소스 검토와 미해결 항목 — 2026-09-26

r35는 성공한 MLO 링크 변경 뒤 공유 TXQ를 다시 스케줄하고, forwarding 경로가 서로 다른 primary 링크의 BSS와 WCID를 조합할 가능성을 줄이는 수정이다. **수정 효과의 범위는 소스에서 확인한 조건부 경로다. Air 절전 복귀 멈춤을 재현하거나 해결했다고 입증한 버전이 아니며, r35는 장비에 설치하지 않았다.** 공유기는 r32이고 추가 무선 시험은 하지 않았다.

기준 자료는 [9월 26일 전체 검토](../mlo-r33/FULL_REVIEW_20260926.md), [r34에서 수정한 항목](../mlo-r34/README.md), [NPU 바이너리 후속 대조](../mlo-r34/FIRMWARE_FOLLOWUP_20260926.md)다. 이전 검토의 F 번호는 유지하되, 당시의 미해결 숫자를 r35의 현재 상태로 인용하지 않는다.

## 이번 변경과 적용 범위

| 변경 | 확인한 문제와 수정 | 남는 경계 |
|---|---|---|
| [0032: 링크 변경 뒤 TXQ 재등록](../../package/kernel/mt76/patches/0032-mt7996-rearm-txqs-after-link-change.patch) | mac80211이 먼저 `valid_links`를 바꾸는 동안 이전 primary의 PS 판단 때문에 공유 TXQ가 active list에서 빠질 수 있다. 성공한 MLO 변경 후 새 primary가 게시된 활성 링크이면 존재하는 station TXQ마다 schedule을 한 번 호출하고 worker를 한 번 깨운다. | 실패한 activation의 mac80211 mask rollback은 callback 반환 뒤라 이 수정이 처리하지 않는다. PS 플래그·AQL gate·완료 경로는 유지하며 non-MLO에는 새 재등록을 수행하지 않는다. |
| [0033: forwarding 링크 조회](../../package/kernel/mt76/patches/0033-mt7996-snapshot-forward-link.patch) | primary selector를 한 번 읽어 VIF와 station 조회에 같은 ID를 사용한다. VIF의 nonzero 링크를 callback의 RCU 문맥으로 조회하고 embedded link 0은 유지한다. 비활성 MLO 링크를 거부하고 마지막 selector/validity 검사에 걸린 변경은 오류로 반환한다. non-MLO의 `link_valid=false`는 계속 허용한다. | 마지막 검사 뒤 변경, selector ABA, 이미 게시한 PPE entry의 무효화를 보장하지 않는다. 링크와 PPE 게시 전체를 하나의 원자적 트랜잭션으로 만드는 수정이 아니다. |

실제 mac80211 `__ieee80211_schedule_txq()`는 active-list lock 아래 아직 등록되지 않은 큐만 넣는다. 따라서 추가 API 호출이 이미 등록된 큐의 중복 삽입이나 재정렬을 뜻하지 않는다. 빈 큐도 한 번 강제 등록될 수 있으나 기존 worker의 PS/AQL 판단을 우회하지 않는다. host fixture의 `rearms` 수치는 API 호출 횟수이며 실제 active-list 공정성이나 동시 실행을 검증한 수치가 아니다.

forward-path caller는 RCU read lock 아래 동작한다. 리뷰에서는 기존 VIF helper가 driver mutex를 요구하는 `rcu_dereference_protected()`를 사용한다는 경계도 확인했다. 최종 0033은 배열 범위를 먼저 검사하고 callback 안에서 `rcu_dereference()`를 사용한다. 다른 mutex 문맥의 공유 helper를 바꾸거나 잠들 수 있는 mutex를 callback에 추가하지 않는다. `mt7996_vif`의 첫 멤버인 embedded link 0의 기존 동작도 보존한다. RCU는 객체 수명 보호이며 selector·BSS·WCID·PPE 전체의 일관성을 자동 보장하지 않는다.

r34의 F02/F03(링크 선택자·WCID 예약 반환), N01(NPU watchdog work 수명), F09/F10(업데이트 UI 재현성과 빈 결과 처리), N02(이전 성공 기록으로 make 생략 방지)는 이어받는다. r35가 이들을 새로 발견하거나 새 펌웨어 바이너리로 해결한 것은 아니다. 빌드·이미지·ABI 검사 절차는 [BUILD.md](BUILD.md)에 별도로 둔다. 소스 시험 통과를 실제 설치·부팅 성공으로 바꾸어 기재하지 않는다.

## NPU 대조에서 확인한 것과 확인하지 못한 것

현재 vendor NPU program은 `TLB7.7.0.0_v03`, SHA256 `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643`이다. Clanker 재구현의 `TLB7.8.0.0_v003`와 혼동하지 않는다. [후속 보고서](../mlo-r34/FIRMWARE_FOLLOWUP_20260926.md)와 [checker](../../tests/check_npu_firmware_paths.py)는 선택된 decoder 807행과 raw anchor 3곳의 바이트를 이 blob에 대조한다. 이는 명령 해석·전체 CFG·실제 실행·무결함의 증명이 아니다.

- Clanker E2의 kite TDMA는 1024개×8바이트 링과 mutex 0을 설명한다. 우리 blob에서 좁힌 `0x840091b4` 함수는 2048개×32바이트 링이며 포화 반환 경로에서 자신이 mutex를 획득하지 않는다. 이 함수에 같은 누락을 귀속할 근거는 없지만 모든 상위 caller의 mutex 소유를 배제한 것은 아니다.
- E3의 전제는 해당 pipeline이 software pool에서 할당하지 않는다는 것이다. 우리 대응 경로에서는 `0x84004d80`의 할당과 `0x84004d0e`의 반환이 같은 pool을 사용한다. 원본 blob 해시·문제 PC가 없는 Clanker 주장과 완전 대응시키지 못했다.
- RRO action 3은 1024개 descriptor의 signature 바이트를 무효화한다. 메모리 해제가 아니다. 특수 selector는 `0x400`이고 wrapper의 상수 응답만으로 NPU와 WM 양쪽의 완료를 보증할 수 없다.
- 기존에 확인한 next-TX-descriptor 무제한 대기와 replacement buffer 할당 선행 경로는 별개의 조건부 관측으로 남는다. 이번 비교가 이를 해소하거나 Air 멈춤 원인으로 확정하지 않는다.

E2/E3의 현재 증상 원인 귀속 확신도는 낮다. 원본 vendor 버전과 경로를 대응시킨 뒤 실제 정체와 같은 시점의 증거가 필요하다. **CPU가 낮고 PPE 가속이 유지됐다는 사실만으로 NPU 문제를 배제할 수 없다.** 미검증 재구현 펌웨어로 교체할 근거도 확보하지 못했다.

## 계속 남아 있는 문제

아래 UI·권한 항목의 재현과 코드 위치는 [기존 F01–F10 표](../mlo-r33/FULL_REVIEW_20260926.md#2-현재-남아-있는-코드배포-문제)에 보존돼 있다. r34/r35의 작은 드라이버 수정으로 해결됐다고 표시하지 않는다.

| 항목 | 남은 문제와 판단 |
|---|---|
| F01 · 조건부 P1 | Wi-Fi 읽기 권한만 가진 위임 계정도 변경 명령을 실행할 수 있는 ACL. 실제 그런 계정이 존재한다는 증거는 없다. |
| F05 · P2 | UCI set/commit 실패를 삼킨 뒤 Wi-Fi를 재시작해 성공으로 오인하거나 불필요한 중단을 일으킨다. |
| F06 · P2 | 비활성 MLO 프로필에도 활성 라디오 두 개를 요구해 저장을 거절한다. |
| F07 · P2 | 편집 대상과 상태 조회 대상 프로필이 달라질 수 있고 꺼진 유일한 프로필의 선택도 유지되지 않는다. |
| F08 · P2 | UCI 이름으로 MLD netdev를 추정하여 사용자 지정 ifname이나 복수 프로필의 상태를 잘못 표시할 수 있다. |
| 실패한 activation rollback | mac80211의 mask 복원 전에 TXQ가 멈춘 경우, 실패 callback은 재등록하지 않는다. 다음 enqueue 같은 별도 wake까지 남을 수 있는 모델 제한을 유지한다. |
| RRO 삭제 오류 무시 | NPU 삭제·WM reset 반환을 버린 뒤 이벤트 항목을 해제한다. WM의 nonzero firmware status도 실패다. timeout recovery work는 존재하며 실제 stale session·Air 원인은 미확정이다. 늦게 완료된 요청과 session 재사용 순서를 모른 채 retry가 안전하다고 가정하지 않는다. |
| PPE 기존 binding 무효화 | 0033은 새 path 조회의 일부 혼합을 막지만 링크 변경 전에 게시된 PPE entry를 제거하지 않는다. 최종 검사와 PPE 게시 사이의 변경도 별도 경계다. |
| PPE SRAM clear 오류 | 하드웨어 항목 삭제 실패 후 객체 정리를 진행할 수 있다. 소유권·FDB 보완이 완전한 오류 재시도까지 제공하지 않는다. |
| Air 간헐 정체 | 과거 실패 기록은 유효하다. 약 2Gbps까지 회복한 CPU/가속 병목과 간헐 멈춤의 원인 규명은 별개다. 이번 소스 검증은 Air 성공 증거를 추가하지 않았다. |

## 새 공개 패치의 판단 유지

이 표는 [9월 26일 조사 시점의 원문·이미지 비교](../mlo-r33/FULL_REVIEW_20260926.md#1-새-공개-빌드와-실제-파일-비교)를 재사용한다. 문서 작성 중 다시 조회한 최신 상태라고 주장하지 않는다.

| 자료 | r35에서의 판단 |
|---|---|
| 일반 UBI2 `ubi2_2026.09.26_r36602-54e453b074` | kernel 6.18.52이며 직전 일반 UBI2와 비교한 펌웨어 12개가 동일했다. 날짜 갱신을 새 NPU/MT7996 바이너리로 세지 않는다. r35가 이 전체 tree를 받아온 것은 아니다. |
| Airoha 995 bridge TTL | 순수 L2 bridge 유형 보완이며 현재 IPv4 HNAPT의 KEEP_TTL을 대체하지 않는다. |
| Airoha 996 cross-ingress guard | L2 MAC 쌍 보호의 병합 후보다. L4 tuple 전체의 격리 보장이 아니며 자체 PPE 소유권·슬롯·FDB 수정을 보존해야 한다. |
| 공식 NPU watchdog `4bdee806` | r34 백포트를 유지한다. probe/remove work 수명 결함 수정이며 Air 절전 정체 해결로 입증된 패치는 아니다. |
| RX31/GRO/ring/DMA 및 mt76 공개 PR | 앞선 조사에서 검토한 미반영 변경은 별도 후보로 유지한다. 이번 0032/0033을 해당 변경 전체의 채택으로 설명하지 않는다. |
| Clanker E2/E3·eagle queue 제한 | 다른 구조·버전의 재구현 자료다. 현재 vendor blob과 실제 W1700K에 동일 결함·효과가 있다는 확인 없이 펌웨어 교체나 성능 개선 근거로 삼지 않는다. |

공식 mt76의 새 MT7996 병합 수정은 기존 조회 범위에서 확인하지 못했으며, 포럼 일부는 접근 실패로 최신 본문을 확보하지 못했다. **포럼에 새 정보가 없었다는 뜻은 아니다.**

## 검증의 경계

전환·forward-path host 검사는 실제 추출 함수를 ASan/UBSan으로 실행하되 커널 객체·락·RCU·MCU와 interleaving을 대체한다. baseline의 예상 실패, 미해결 조건을 확인하는 assertion, 후보의 통과 수치를 서로 구분해야 한다. RCU helper 계약은 host stub만으로 검증할 수 없으며 실제 caller와 소스를 함께 검토해야 한다.

r35 장비 설치·부팅, 추가 무선 시험, Air 절전 복귀 성공, WAN/IPv6/UDP/VLAN/QoS/Tailscale 전체 기능 검증은 수행하지 않았다. 소스에서 닫은 제한된 경계와 이 미검증 범위를 함께 유지한다.
