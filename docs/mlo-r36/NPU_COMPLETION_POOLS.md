# NPU-02: 교체 버퍼와 TX completion 풀 후속 분석

분석일: 2026-09-26. 실기기 접속·계측·무선 시험·펌웨어 변경 없이 기존 vendor 바이너리, 저장된 디코딩, FDK와 prepared host 소스를 읽었다. 공개 소스 패치나 빌드를 변경하지 않았다.

본문의 `../npu-firmware-audit-*`, `../mlo-link-transition-*`, `source-cache/`는 공개 저장소에 포함되지 않는 로컬 원본 위치다. 공개 재현에는 [BUILD.md](BUILD.md)의 이미지 추출본과 decoder 생성 절차를 사용한다.

**결론:** 교체 버퍼 부족이 TXdone과 TX token 회수를 지연시키는 순서는 확정돼 있다. 이번에는 서로 다른 두 풀과 독립적인 교체 버퍼 반환 경로를 확인했다. 할당 실패 하나만으로 영구 교착을 입증할 수 없다. Air 절전 복귀 stall과의 귀속은 계속 미확정이다.

## 기준과 검증 범위

- 원본: `../npu-firmware-audit-2026-09-22/research/upstream-airoha-en7581_MT7996_npu_rv32.bin`
- vendor 문자열: `TLB7.7.0.0_v03`; 로드 기준 `0x84000000`; 크기 122,336 bytes.
- SHA256: `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643`.
- 기존 `installed-rv32.instructions.json`의 선택 11구간·1,356행을 원본 bytes와 대조했다. 핵심 PC 58개의 opcode와 RRO action6 table entry를 [completion-pools-verification.json](completion-pools-verification.json)에 기록했다.
- blob 1byte 변경, decoder row 변경의 음성 대조군 2개는 모두 거부됐다. 이 수치는 실기기 시험이나 instruction 의미 검증의 통과 수가 아니다.
- 선형 디코더가 지원하지 않는 vendor custom instruction은 의미를 해석하지 않았다. 예를 들어 `b19a/b19c`, `b3ba/b3bc`의 분할 결과를 실제 compressed branch로 취급하지 않는다. 주소·바이트 일치는 독립적인 재디코딩이나 firmware 정상 실행의 증명이 아니다.

재실행: workspace root에서 다음 명령을 실행한다. 기존 바이너리와 decoder JSON을 읽고 결과를 stdout으로 출력한다. 별도 binary/전체 disassembly 사본을 만들지 않는다.

```sh
python3 docs/mlo-r36/check-completion-pools.py --blob "$NPU_PROGRAM" --instructions "$DECODER_JSON"
```

## 1. 두 풀은 역할과 배열이 다르다

| 자원 | 원본 opcode 근거 | 범위·용량 |
|---|---|---|
| 교체 패킷 버퍼 P | allocate `4d80`, release `4d0e`, 배열 포인터 `gp+0x7e0`, producer `gp+0x7d8`, consumer `0x3e901ba4` | `4ed0–4eda`가 ID `0..0x3fff`를 초기화. 16,384개 u16 entry |
| 완료 TX token T | allocate `4c16`, release `4b96`, 배열 포인터 `gp+0x7dc`, producer `gp+0x7ec` | 초기 backing array는 `4ef4–4efe`의 0x7000개. 실제 wrap/유효 범위는 `gp-0x7e8` 설정값 |
| host의 T 설정 | prepared mt76 `mt7996/npu.c:232–237`, `mt7996/mt7996.h:98` | `WLAN_FUNC_SET_WAIT_TOKEN_ID_SIZE`에 `MT7996_HW_TOKEN_SIZE=8192` 전달. 이번에는 실기기 mailbox 값·잔량을 읽지 않음 |

표와 이후 본문의 짧은 주소에는 모두 `0x8400` prefix를 붙인다. 예: `4d80`은 `0x84004d80`이다.

P allocator는 `(consumer + 1) % 16384 == producer`일 때 실패한다(`4dc0`). 초기 두 index가 0이면 16,383개의 연속 할당이 가능하고 한 entry를 보존한다. 고정 RX ring 등이 이미 할당한 양은 별도로 차감해야 한다. 따라서 16,383을 동작 중 free-buffer 잔량으로 해석하면 안 된다.

TXdone의 `b308/b342 → 4b96`는 **T만 반환한다.** 이 반환을 앞으로 옮겨도 P의 부족을 직접 해소하지 못한다. token 반환 순서만 바꾸는 firmware 수정은 제안하지 않는다.

## 2. 성공·실패 시 소유권과 실제 재사용 순서

1. `b100 → 4d80`에서 새 P를 얻는다. 실패하면 `b108 → b424 → b430 → b298`로 반환하여 token parser와 완료 descriptor 갱신에 도달하지 않는다.
2. 성공한 경우 기존 descriptor의 P ID를 읽는다(`b13e`). type6/24 completion parser에서 T를 반환한다(`b308/b342`).
3. 기존 descriptor의 P ID map을 교체한다(`b1ae`). 이전 P를 packet queue에 넣는다(`b1e8 → ac30`). enqueue 실패 시 이전 P를 즉시 반환한다(`b408 → 4d0e`).
4. descriptor 주소·control을 새 P로 갱신한다(`b20c/b216`). completion index publish는 16개 처리마다 수행된다(`b24e–b262`).
5. enqueue 성공 시 이전 P의 반환은 이후 packet consumer 등으로 넘어간다. T와 P가 같은 release 호출에서 동시에 반환되는 구조가 아니다.

원본 ring 산술만 재현한 제한 모델 5개 사례는 모두 통과했다. P 초기 16,383회 할당 후 10,000회 반복 실패, 합법적으로 빌린 T 반환 뒤 P 실패 유지, P 한 개 반환 후 재진행을 검사했다. 처음 반환한 P ID가 0이어도 다음 할당은 보존됐던 ID 16383이며, 두 번째 반환 뒤 ID 0이 재사용된다. 즉 반환한 ID를 즉시 재사용한다고 가정할 수 없다.

모델은 합법적 반환을 전제한다. 실제 총 점유량에 도달할 수 있는지, mutex/메모리 순서, 중복 반환, MMIO, worker 공정성, 다른 RX worker의 경쟁 할당은 모델링하지 않았다.

## 3. TXdone 외에도 P 반환 경로가 있다

**PPE result interrupt:** 함수 `8f6e`는 FIFO count `0x1fb50fe4`, record `0x1fb50fe0`을 읽는다. record bit16이 설정되면 `8fae → 4d0e`로 P를 반환한다. 별도의 P 할당을 요구하지 않는다. 다른 record를 enqueue하다 실패한 경우에도 `9008 → 4d0e`로 반환한다. FIFO pop/ack는 `8fbe/901a`에서 수행한다.

이는 단순히 호출되지 않는 함수가 아니다. `98a2`에서 interrupt source `0x5f`를 지정하고, `98b4/98b8`에서 callback `8f6e`를 계산한 뒤 `98d0 → 3254`로 등록한다. 다만 실제 IRQ 활성·도착 여부를 확인한 것은 아니다.

**이미 큐에 있는 유효 패킷 소비:** `a3f6`은 512-entry, entry 12-byte의 packet queue에서 유효하고 길이가 0이 아닌 패킷을 host RX로 전달한다(`a570 → f8be`). 성공 분기와 실패 분기는 모두 `a58c → 4d0e`의 P 반환에 합류한다. host RX ring full은 `f95e → f986`, `fa04 → fa2a`를 통해 `-1`로 반환하므로, 이 full 조건 자체가 P를 무한 보유하는 경로는 아니다. 전송 내부의 모든 MMIO·copy가 항상 완료된다는 증명은 하지 않았다.

packet consumer는 slow-path loop의 `e500/e510`에서 호출된다. TXdone loop는 `d172 → b0a6` 반환 후 재시도한다(`d17a/d19e`). P allocation 실패 경로는 allocator 해제 호출 `4e14 → 651c` 후 `-1`을 반환한다. 따라서 P 부족만으로 그 worker가 mutex를 잡은 채 영원히 기다린다고 해석할 수 없다.

## 4. 장기 정체에 필요한 추가 조건

P가 비고 pending TXdone이 있는 상태에서, P를 반환할 모든 실행 가능한 경로가 장기간 진행하지 못하거나 반환 대상 자체가 없어야 정체가 지속된다. 반환이 있더라도 다른 RX worker가 계속 먼저 할당하는 starvation 가능성은 별도로 남는다.

현재 부족한 근거는 전체 P 소유권 합계, 각 RX/RRO/packet queue의 실제 점유량, 반환 FIFO 항목과 IRQ 진행, 소비자 gate·PC, 정체 순간의 index다. 검토한 반환 경로 중 하나라도 합법적인 P를 공급하고 TXdone이 이를 획득하면 제한 모델의 고갈 상태에서 벗어날 수 있다. 반대로 재시도만으로 새 P가 생기지는 않는다. 이 조건 분석은 실제 영구 교착의 도달 가능성 증명이 아니다.

## 5. mailbox reset은 보장된 복구가 아니다

RRO table base `0x8401bd64`, action6 entry `0x8401bd7c`의 원문 `3e23ffff`는 target `0x8400e0a2`를 가리킨다. 해당 진단 문자열은 `run buf id reset`이다.

- `e0ae → 990e`: MMIO `0x1fb5080c`가 저장된 index와 같아지기를 반복해서 기다린다(`993c`).
- `e0b2 → 9960`: FIFO count `0x1fb50fe4`의 하위 16bit가 0이 되기를 기다린다(`997e/99a6`).
- 대기가 끝나야 `9992 → 4e1c`가 P 배열과 index를 초기화한다. 위 두 대기에는 자체 시간 제한이 없다.

따라서 FIFO/index가 진행하지 않는 상황에서는 명시적인 buffer reset 요청도 완료되지 않을 수 있다. NPU-02 allocation 실패 분기에서 이 reset을 자동으로 호출하는 연결은 확인하지 못했다.

prepared host `drivers/net/ethernet/airoha/airoha_npu.c:170–216`의 mailbox poll은 약 500ms 후 실패를 반환한다. 이는 firmware 명령 취소·완료·NPU 재시작을 뜻하지 않는다. 같은 파일의 WDT handler/work(`321–358`)는 PC/SP/LR coredump를 만들며, 검토한 함수 자체에는 자동 재시작이 없다. SoC 전체의 모든 watchdog 동작을 배제하는 결론은 아니다. 실제 stall과 mailbox timeout의 동시 발생 역시 미확인이다.

## 6. FDK 대응과 차이, 남는 판단

FDK `2d13e291ab511b6b319dc5073f47e26cac958ae4`의 `packet_id_pool.c`, `mt7996_tx_done.c`, `mt7996_packet_queue_consumer.c`, platform callback, `rro_control.c`를 역할 대조에 사용했다. FDK는 원본 vendor C 소스나 동일 바이너리가 아니다.

특히 FDK는 pool 설정·packet ID 범위·ring full·callback 결과를 검사한다. 원본 `4d0e`는 producer 위치에 쓰고 index를 전진하며, FDK `packet_id_pool_release()`의 `next_producer == consumer` 거부 분기를 포함하지 않는다. FDK의 검사·복구·유한 poll 보장을 vendor에 그대로 적용하지 않았다. 이 차이만으로 실제 중복 반환이나 손상을 확정하지도 않았다.

풀 분리, 독립 반환 경로, reset 대기 구조의 확신도는 높다. 영구 교착 도달 가능성과 Air stall 귀속의 확신도는 낮다. **CPU 사용률이 낮고 PPE 가속이 유지된다는 사실만으로 NPU 문제를 배제할 수 없다.** 현재 결과는 정상 실행·무결함·stall 수정의 증명이 아니며, 기존 NPU-01 무제한 next-descriptor 대기 역시 별도의 미해결 조건부 경로로 남는다.
