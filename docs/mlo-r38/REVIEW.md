# r38 PPE 초기화와 NPU 복구 경계 검토 — 2026-09-26

## 수정한 결함과 영향

`airoha_ppe_flush_sram_entries()`의 반복문 내부 `int err`가 함수 반환에 쓰는 `err=0`을 가렸다. SRAM commit 오류는 반복을 중단시키지만 함수는 성공을 반환하여 PPE와 Ethernet 초기화를 계속했다. [9999-z5 패치](../../target/linux/airoha/patches-6.18/9999-z5-net-airoha-ppe-propagate-sram-flush-error.patch)는 내부 선언만 제거한다. 정상·0개 항목은 기존처럼 0, 오류는 첫 실패 값을 반환하고 이후 항목을 건드리지 않는다.

이 오류는 probe 초기화 경로의 확정 결함이다. **이미 가동 중인 Air의 순간 정체 원인으로 연결된 증거는 없다.** 실제 SRAM 초기화에 실패하면 Ethernet probe도 실패하는 것이 의도한 변경이며, 무조건 동작을 계속하게 하는 fallback을 넣지 않았다.

공식 이력도 추가 대조했다. 이 코드는 기존 [099-08 백포트](../../target/linux/airoha/patches-6.18/099-08-v6.19-net-airoha-ppe-Flush-PPE-SRAM-table-during-PPE-setup.patch)가 가져온 `620d7b91aadb`에서 유입됐다. Wayen.Yan의 [공식 수정 d7d81b003013](https://github.com/torvalds/linux/commit/d7d81b00301398fcd38cf5b5869f0fdb674472ef)은 **2026-06-13에 이미 병합**됐지만 현재 백포트에는 빠져 있었다. 오늘 새로 공개된 패치로 세지 않는다. 공식 v2는 외부 err를 없애고 즉시 오류를 반환하며, r38은 내부 선언을 없애 기존 break/반환 경로를 유지한다. 같은 오류 전파를 겨냥한 최소 수정이며 정확한 cherry-pick으로 표시하지 않는다. 공식 v2도 보존한 r37 소스에 fuzz 0으로 적용해 같은 16개 검사를 통과했다. [출처·해시·대조 결과](UPSTREAM_PPE_FIX.json)를 보존했으며 비교를 위해 진행 중 빌드의 입력을 변경하지 않았다.

r37 prepared `linux-6.18.44` 기준으로 모든 호출자를 확인했다.

- `airoha_ppe.c:1441 → :1698`의 PPE init만 이 helper를 호출한다.
- `airoha_eth.c:1830`의 hw init으로 오류가 전달되고 `:1838`에서 기존 QDMA cleanup 후 `:4090/:4146`의 probe 오류 정리로 이어진다.
- `DEV_STATE_INITIALIZED` 설정·NAPI 시작·포트 등록 전이다. QDMA global config에는 아직 TX/RX DMA enable 비트가 설정되지 않았다. IRQ handler는 초기화 비트가 0이면 NAPI에 접근하지 않는다.
- SRAM commit `airoha_ppe.c:752–770`은 CPU가 shadow entry를 MMIO에 복사하고 ACK를 기다린다. 하드웨어에 이 임시 host buffer의 DMA 주소를 넘기는 경로가 아니다.
- flow hash table 초기화보다 앞서 반환하므로 미초기화 table을 deinit하지 않는다. IRQ dev_id인 eth와 register mapping은 IRQ devres보다 오래 유지된다.

[기존 PPE 검사](../../tests/test_airoha_ppe_ownership.py)를 확장해 실제 추출 함수로 0개·전체 성공·첫/중간/마지막 오류를 검사했다. 기존 11건을 유지하며 후보는 16 PASS, 원본은 13 PASS와 정확한 false-success 기대 실패 3건이다. ASan/UBSan에서 오류가 없었다. ACK·MMIO는 대체 함수이며 완전한 probe·IRQ 동시성·하드웨어 검증은 아니다.

## 기존 Air 실패 기록이 지지하는 범위

9월 25일 r32 Air 절전 복귀 시험은 사용자 1914 / 0 / 2041Mbps와 잠깐 멈춤으로 기록돼 있다. 시험 중 새 kernel message는 0개였고, 저장 자료에 MCU timeout·SER·NPU reset 실행을 가리키는 로그는 없다. mailbox/reset 전용 trace를 수집하지 않았으므로 이들이 절대 발생하지 않았다는 증명은 아니다.

약 1초 LAN 집계 최저 bin은 184.661Mbps다. 앱의 정확한 멈춤 시각·길이가 없으므로 이 bin을 앱의 멈춤이라고 확정하지 않는다. 인접 상세 표본에서 NPU RX queue head는 진행하고 TX queued는 0이었다. RX queued=511은 수신용 게시 버퍼 수로, ring 포화의 증거가 아니다. PPE 52/52 표본의 8개 binding 유지도 packet/ACK 진행을 증명하지 않는다.

PS trace를 켠 후속 Air 회차(1715 / 1336 / 1987Mbps)는 멈춤이 없었고, 그때도 status2와 PS 전환이 관측됐다. 따라서 신호의 존재만으로 원인을 판정하지 않는다. 의도적 Mac 재연결·복구 관측을 Air 실패 자료와 합치지도 않는다. 원본 시간·수집 공백의 상세 분석은 [r36 계측 경계](../mlo-r36/AIR_EVIDENCE.md)에 보존돼 있다.

기존 r22–r31 자료도 보고서·메타데이터로 선별했다. r22 실패는 미러링 사용, r29의 1105/0/1370Mbps 실패는 사용자 정정상 18 Pro라 Air 인과 근거에서 제외한다. Air로 확인된 r29 전체 TCP·절전 후 캡처는 ACK 정지 250ms 초과가 없는 정상 회차다. r19의 보존된 실패에서는 재전송 16개가 LAN→AP 출력까지 최대 0.125ms로 전달됐지만 기기 모델은 “iPhone”만 기록돼 Air로 재분류하지 않는다. 당시 양 링크 PS1과 ACK 정체는 상관관계이며 무선 수신·firmware 실행 성공을 증명하지 않는다. 기존 자료에서 Air 실제 실패와 전체 TCP·동시 NPU 상태를 모두 갖춘 회차는 확보하지 못했다.

## NPU 실패 처리에 단순 return을 넣지 않은 이유

현재 mt76 `01367e60`의 `mt7996/mac.c:2672`는 stop 오류를 버리고 DMA reset·token 반환으로 진행하며 `:2744`의 재초기화 실패도 무시한다. 이는 [r37의 미해결 결함](../mlo-r37/REVIEW.md)으로 유지한다. 반대로 작은 return 하나로 안전한 복구가 완성되지는 않는다.

| 다른 진입점 | 단순 정지 상태만으로 해결되지 않는 이유 |
|---|---|
| common `mac80211.c:1078–1080` | 채널 설정 오류에도 RESET을 지우고 worker를 켠다. |
| `mt7996/main.c:733,2757` | watchdog을 다시 예약하고 reconfiguration 완료에서 queue를 깨운다. |
| `mt7996/mcu.c:476–479`, `mac.c:2855` | 일반 reset 진입 검사를 우회해 reset work를 직접 예약한다. |
| full reset `mac.c:2427–2430` | NPU stop 없이 token 반환·DMA reset을 수행한다. |
| 제거 `mt7996/init.c:1853–1854` | token과 DMA 정리를 진행하므로 실패한 runtime 호출만 중단해도 수명 문제가 남는다. |

stop helper는 내부 mutex를 잡으므로 SER의 mutex 구간 안으로 단순 이동하면 자기 교착이다. NAPI를 비활성화한 채 반환하면 다음 reset/remove에서 중복 disable로 기다릴 수 있다. mutex 안의 `cancel_delayed_work_sync()`도 mac_work의 같은 mutex 대기와 충돌한다. 마지막 init action7의 timeout은 명령이 실행되지 않았다는 뜻이 아니므로 이미 공개한 DMA buffer를 반환해도 된다는 근거가 아니다.

이 경로에는 실패 상태·NAPI 상태·재진입·제거와 실제 DMA 중지 계약을 함께 정의해야 한다. r37의 mailbox `-EBUSY`는 이전 요청의 메모리를 보존하며 NPU 전체 정지를 보장하지 않는다. 현재 실패 로그에서 SER 발생이 입증되지 않았으므로 이 결함을 Air 멈춤의 원인으로 승격하거나 무검증 자동 reset을 추가하지 않았다.

## 실제 NPU 펌웨어의 정지 응답

기존에 보존한 vendor RV32 program 122,336바이트와 data 3,084바이트를 다시 디코딩했다. program SHA-256은 `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643`, data는 `61a75afb052feed2ceb2f3023e16f50317c05c78f9c8e564bf01924ce39c7ec1`이다. firmware 변경·실행이나 장치 접근 없이 [검사 코드](check_stop.py)와 [결과](STOP_VERIFICATION.json)를 보존했다.

호스트 `mt7996_npu_hw_stop()`의 순서는 SET command 24/ifindex 4 → GET command 0/ifindex 3을 최대 10회 → SET command 24/ifindex 6이다. 10은 GET command 번호가 아니라 반복 횟수다. 아래 주소는 program load base `0x84000000` 기준이다.

| 단계 | 바이너리에서 확인한 동작 | 판단의 한계 |
|---|---|---|
| action 4 (`0x8400e220`) | stop byte를 1로 쓰고 worker gate들을 0으로 만든다. | 이 함수 자체는 DMA idle을 검사하지 않는다. |
| GET ifindex 3 (`0x8400d80e`) | `word[0x3e9046e8] OR !byte[0x3e9046f6] OR !byte[0x3e9046f7]`를 반환한다. worker들은 gate 조건에 따라 해당 상태/확인 값을 쓴다. | 반환값 0은 이 worker 확인 조건이며 전역 DMA 중지 비트가 아니다. |
| action 6 (`0x8400e0a2`) | `0x8400990e`에서 MMIO `0x1fb5080c`와 RAM `0x3e9046c0` 일치를 기다리고, `0x84009960`에서 MMIO `0x1fb50fe4` 하위 16비트가 0이 되기를 기다린 뒤 P/T pool을 초기화한다. | 뒤로 돌아가는 polling 분기에 로컬 timeout이 없다. 외부 호출과 MMIO 진행은 모델링하지 않았다. |
| SET wrapper (`0x8400fc2c`) | action 함수가 반환한 뒤 성공 응답을 만든다. | 정상 action 6 완료는 위 검사/초기화의 근거지만 모든 WFDMA·RRO·NPU DMA 중지를 입증하지 않는다. |

따라서 호스트 timeout이나 r37의 `-EBUSY`만으로 firmware 작업이 취소됐거나 DMA 메모리를 반환해도 된다고 판단할 수 없다. 반대로 이 경로가 Air의 실제 멈춤 때 실행됐다는 증거도 없다.

Capstone 5.0.7로 15개 범위의 260개 명령, 62개 바이트/명령 기준점, 18개 계산된 RAM/MMIO 주소, 16개 분기/호출 대상을 대조했다. program·action table·wrapper pointer를 바꾼 세 음성 대조군은 각각 지정한 이유로 거부됐다. 동일 입력 재실행 결과도 일치했다. TXdone 하위 함수의 SYSTEM/vendor word `738029fc` 두 곳(`0x8400b19a`, `0x8400b3ba`)은 해석하지 못한 상태로 명시했다. 이 검사는 전체 호출 그래프·동시성·DMA 소유권의 증명이 아니다.

보존한 원본을 가진 환경에서는 아래처럼 재현한다. 검사기는 입력을 수정하지 않으며 JSON을 표준 출력으로 보낸다. Capstone이 기본 Python 환경에 없다면 기존 설치 경로를 `--capstone-path`로 지정한다.

```sh
python3 docs/mlo-r38/check_stop.py \
  --program /path/to/en7581_MT7996_npu_rv32.bin \
  --data /path/to/en7581_MT7996_npu_data.bin \
  --instructions /path/to/installed-rv32.instructions.json
```

## 빌드 경고 대조

최종 9단계가 모두 종료 코드 0으로 끝났지만 전체 로그에는 경고 1,074회·고유 308개가 있다. [전체 목록](BUILD_WARNINGS.json)을 별도 보존했다. r37 대비 새 문구 두 개는 `coova-chilli`의 `depmod`와 `xtables-addons`의 `/bin/true` 요구 경고였다. 해당 외부 모듈은 추출한 이미지에 없고, 이미지의 74개 모듈 inventory·payload·ABI를 직접 대조해 `airoha-eth.ko` 이외 73개가 r37과 같은 것을 확인했다. 경고가 없는 빌드나 모든 경고가 무해하다는 판정으로 표시하지 않는다.

## 남은 범위

9월 26일 전체 검토의 번호를 그대로 추적한다. [r33 최초 목록](../mlo-r33/FULL_REVIEW_20260926.md)은 당시 상태이며 아래 후속 수정 상태와 함께 읽어야 한다.

| 범위 | r38 소스 기준 상태 |
|---|---|
| F02/F03 링크 선택자·WCID 누수 | r34 수정과 r35 링크 전환 보강 포함, host 회귀 검사 유지 |
| F04 브리지 가속 규칙 갱신 | 기존 수정 유지; 허용한 IPv4 TCP/포트 범위라는 제한 유지 |
| F09/F10 업데이트 UI 재현·빈 결과 처리 | r34 공개 feed patch와 설치 이미지 UI 검사 유지 |
| N01 watchdog work 초기화/해제 | r34 공식 백포트 유지. 별도의 공유 IRQ·runtime 정지 수명 문제까지 해결한 것은 아님 |
| N02 과거 빌드 성공 기록 재사용 | r34 이후처럼 r38도 9개 make 단계를 모두 실행 |
| F01, F05–F08 | 위임 계정 실행 권한, UCI 실패 후 재시작, 비활성 프로필 저장, 프로필 선택, 사용자 지정 ifname 상태 조회는 미해결 |
| NPU·PPE runtime 실패 처리 | stop/reset·RRO 오류 무시, DMA 소유권·공유 IRQ 수명, SRAM 삭제 실패는 미해결 |
| Air 절전 복귀 순간 정체 | 기존 실패는 유효하나 원인과 해결은 미확정. 추가 무선 시험은 종료 |

runtime PPE SRAM 삭제 실패, NPU IRQ 수명·stop/reset·RRO 오류 처리와 F01/F05–F08 설정·권한 문제는 남아 있다. 이번 수정은 초기화 flush 오류만 전파한다. 위 공식 PPE 수정은 이번에 새로 조회했고, 나머지 공식 패치·포럼 정보는 [9월 26일 r37 재조회](../mlo-r37/REVIEW.md#최신-공식-패치-재조회)를 재사용한다. 추가 무선 시험·공유기 접속·설치·재부팅은 하지 않았다.
