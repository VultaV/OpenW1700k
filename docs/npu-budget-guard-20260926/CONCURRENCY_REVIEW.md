# Zero-budget guard의 consumer index 동시성 검토

2026-09-27. **확인된 hart2 / band 0·1 호출에서는 새 동시 writer를 찾지 못했다. 기존 양수 예산의 입력 없음 경로도 index를 읽었다가 같은 값으로 재저장한다.** 따라서 이 store 자체는 4바이트 후보가 새로 도입한 동작이 아니다. 다만 firmware 전체의 간접 호출·동시 reset·interrupt 계약까지 증명한 것은 아니다. 기존의 “동일 index writer가 존재한다”는 정적 발견만으로 후보에 새로운 경쟁 조건이 있다고 결론내릴 수 없다.

원본 program은 122,336 bytes, SHA256 `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643`이며 현재 r42 추출본과 같은 입력이다. data SHA256은 `61a75afb052feed2ceb2f3023e16f50317c05c78f9c8e564bf01924ce39c7ec1`이다. 후보는 그대로 offset `0x9e1a`의 `9374f50f → e284e1c5` 4바이트이며 이번 작업에서 변경하거나 실행하지 않았다.

## 실제 저장 주소와 caller

부팅 `0x84000018/1c`가 만드는 실제 `gp`는 `0x3e9013a8`이다. 배열 `gp+0x3d4+4*queue`의 queue 0·1·2 주소는 각각 `0x3e90177c`, `0x3e901780`, `0x3e901784`로 분리된다.

| 함수 / store PC | 확인된 역할과 호출 범위 |
|---|---|
| `9da4` / `9ef4` | `ed8c`는 queue 1, `edd6`은 queue 0을 고정한다. 두 직접 caller `ed8e`, `edd8`는 `ec48` worker 안에 있다. hart dispatch table index 2 → `013e → 01a0 → ee0a → ec48` 경로다. |
| `a15a` / `a1a6` | 직접 caller `136a` 앞의 `1366`이 queue 2를 고정한다. 이 확인된 호출의 store는 queue 0·1을 덮어쓰지 않는다. 이 caller의 모든 상위 hart 배정을 증명했다는 뜻은 아니다. |
| `9b34` / `9b80` | 같은 배열에 저장할 수 있는 별도 generic consumer다. 아래 제한된 조사에서 들어오는 직접 분기나 절대 함수 포인터를 찾지 못했다. |
| `9ba0` / `9cd8` | 같은 배열의 별도 batch consumer다. 저장 명령 `23a09d01`은 확실하지만, 현재 실행 caller·hart·queue 값은 확인되지 않았다. 현재 활성 TX 경로의 경쟁 writer로 계산하지 않는다. |

주소 표의 짧은 PC에는 `0x8400` prefix를 붙인다. 저장 디코딩 44,253행의 경계에서 실제 raw RV32 JAL/B/CJ/CB offset을 계산했다. `9b34..9ba0`, `9ba0..9da4`에 외부에서 들어오는 해당 직접 분기는 0개였다. program/data에서 두 entry의 little-endian 절대 주소도 0개였다. 이는 **dead code 증명은 아니다**. PC-relative table, 동적 함수 포인터, custom 명령, 미확인 중간 진입은 배제하지 않는다.

## 기존 양수 예산에서도 같은 재저장이 있다

다음은 실제 표준 명령과 raw branch offset으로 확인한 기존 경로다. 입력 descriptor bit31이 0이고 진단용 word `0x3e904640 != 1`인 경우에는 외부 함수 호출 없이 진행한다.

1. `9db2` (`83ad0700`)가 consumer index를 `s11`로 읽는다.
2. `9e14`는 반환 카운터를 0, `9e16`은 pending batch `s7`을 0으로 둔다.
3. `9e2e`가 descriptor control을 읽고 `9e32` (`63d90c16`)가 입력 없음이면 `9fa4`로 간다.
4. `9fb0` (`e318f7f2`)는 위 word가 1이 아니면 `9ee0`으로 간다. `s7=0`이므로 batch 게시 없이 `9ee4`로 진행한다.
5. `9ef4` (`2320bd01`)는 처음의 `s11`을 원래 배열 slot에 저장하며 `9ef8`에서 반환값 0을 만든다.

4바이트 후보의 zero 경로는 descriptor/진단 word 읽기보다 일찍 같은 epilogue로 간다. 새 allocator 호출·descriptor ownership 게시·MMIO write·새 배열 주소를 추가하지 않는다. 레지스터·스택 복원은 기존 [GUARD_DESIGN.md](GUARD_DESIGN.md)의 제한 실행 검사가 유지하는 계약이다. 양수 경로에는 명령 하나가 늘므로 cycle·interrupt timing 동일성은 주장하지 않는다.

## 초기화·reset 한계와 최종 판정

hart0의 부팅 `0088..009c`에는 조건부 clear loop가 있다. `word[0x1ec0c140] != 0xffffffff`일 때 `0096`이 `[0x3e900c10,0x3e904754)`를 4바이트씩 지우므로 이 배열도 포함한다. 정상 초기화 경로라는 사실과, 운영 중 다른 hart만 재시작되어 같은 clear가 겹치지 않는다는 보장은 다르다. 검토한 WLAN action4/7은 worker 상태·stop flag를 변경하며 해당 배열에 직접 저장하지 않는다. `ec48`의 stop/reconfigure 대기는 자체 stack의 cached DMA index를 초기화한다. 이 근거만으로 전역 quiesce나 모든 간접 reset 동작이 증명되지는 않는다.

현재 host `airoha_npu.c`에서 firmware 복사와 boot trigger는 probe 경로에 있고, WDT work는 register dump를 수집한다. 이 두 경로에서 정상 TX 도중 consumer 배열을 직접 재설정하는 별도 host writer는 확인되지 않았다. 하드웨어의 비문서화된 reset 동작까지 배제한 것은 아니다.

가정상 다른 actor가 index를 `7 → 8`로 바꾸면 이전에 7을 읽은 epilogue가 7로 되돌릴 수 있다. **그 actor의 현재 동시 도달은 입증되지 않았고, 위 기존 양수/no-input 경로도 같은 반례에 노출된다.** 따라서 결과는 “확인된 정상 소유권 경로에서 추가 경쟁 위험 근거 없음, 전역 소유권/reset 계약은 미증명”이다. 후보의 전체 동시성 안전·실제 boot 동작·Air 정체 해결을 입증한 것으로 사용해서는 안 된다.

검사 입력과 PC/raw bytes, 11개 구간의 기존 Capstone dylib fresh decode 685개, 직접 분기·절대 포인터 조사 결과는 [CONCURRENCY_VERIFICATION.json](CONCURRENCY_VERIFICATION.json)에 있다. Python Capstone 패키지 파일이 없어서 기존 dylib의 `cs_open/cs_disasm` API를 사용했다. 새 설치·firmware 실행·라우터 접근은 하지 않았다. 이 JSON의 PASS는 제한된 byte/정적 계약 대응이며 동시 실행 PASS가 아니다.
