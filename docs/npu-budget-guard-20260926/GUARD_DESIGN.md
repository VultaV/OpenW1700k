# Vendor NPU zero-budget guard의 메모리 내 후보 검사

2026-09-26. 실제 vendor program을 읽어 **메모리 사본의 4바이트만** 바꾼 뒤, 함수 앞부분과 기존 복귀 경로의 표준 RV32 명령을 제한적으로 실행했다. 수정된 firmware 파일을 만들거나 배포·설치하지 않았다. 검증 코드·문서 외의 제품 소스와 공유기 상태도 바꾸지 않았다.

정상 함수 진입과 band 0·1의 유효한 테이블/스택을 전제로, 후보는 양수 예산에서 검사한 두 지점의 상태를 보존하며 예산 0에서는 descriptor 처리 전에 0을 반환한다. **consumer index를 같은 값으로 다시 저장하는 기존 동작은 남는다.** 전체 firmware, 동시성, 실행 시간, Air 절전 복귀 멈춤 해결은 검증하지 않았다.

## 원본과 4바이트 후보

- 원본: r36 추출 rootfs의 `lib/firmware/airoha/en7581_MT7996_npu_rv32.bin` (동일 SHA의 기존 vendor 추출본과 일치), 122,336 bytes, 로드 기준 `0x84000000`.
- 원본 SHA256: `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643`.
- 메모리 후보 SHA256: `389cfecb074fc21c163006c791b65f9628fe790cfb682f2e288b71c14104a736`.
- 파일 offset `0x9e1a`: `9374f50f` → `e284e1c5`. 크기와 나머지 코드는 유지한다.

| PC | 원본 | 후보 |
|---|---|---|
| `0x84009e1a` | `andi s1,a0,0xff` (4 bytes) | `c.mv s1,s8` (2 bytes) |
| `0x84009e1c` | 위 명령의 중간 | `c.beqz a1,+0xc8` (2 bytes), 대상 `0x84009ee4` |

`0x84009df2`에서 이미 `s8=a0&0xff`를 계산하며 검사한 앞부분에서 `s8`, `a0`, `a1`은 이 교체 지점까지 유지된다. 따라서 양수 `a1`에서는 같은 `s1`을 만든 뒤 원래 `0x84009e1e`로 진행한다. 0에서는 기존 epilogue로 분기한다. 원본의 unsigned 예산 상한 128도 보존된다. 이전 clang RV32 assembler 실행은 실패했으며 성공한 검증으로 계산하지 않았다. 별도 raw encoding 대조는 [ENCODING_VERIFICATION.json](ENCODING_VERIFICATION.json)에 있다.

## 검사 방법과 수치

[check_guard.py](check_guard.py)는 원본 hash와 저장 디코딩 JSON의 선택 byte를 먼저 확인하고, 실제 원본과 메모리 후보를 기존 Capstone으로 새로 디코딩한다. 저장된 mnemonic/operand 문자열을 실행 입력으로 사용하지 않는다. 실행 허용 구간은 `[0x84009da4,0x84009e26)`, `[0x84009ee4,0x84009f14)` 두 곳뿐이다. 지원하지 않는 명령·구간 이탈·초기화하지 않은 메모리 읽기·허용되지 않은 외부 쓰기는 즉시 실패한다.

합성 레지스터 값, 112-byte 스택, consumer index, pointer table 값을 사용한다. 실제 firmware RAM이나 descriptor/allocator/MMIO를 모사하지 않는다. 외부 읽기는 index와 pointer table 두 주소로 제한하고, 외부 쓰기는 index 주소만 허용한다. 예산마다 레지스터 표식과 합성 index를 바꾼다.

입력 예산은 `0..65535` 전부와 `0x10000`, `0x10001`, `0x7fffffff`, `0x80000000`, `0xfffffffe`, `0xffffffff`다. 전체 32비트 공간을 전수 조사한 것은 아니다.

| 검사 | 실제 결과 |
|---|---:|
| 원본 byte 대응 및 fresh decode | 68개 명령 |
| 메모리 후보 fresh decode | 69개 명령 |
| 정상 band 0·1 양수 예산 | 131,082 통과 / 0 실패, 100% |
| 위 양수 입력의 `9e1e`·`9e26` 상태 비교 | 262,164 지점 일치 |
| 정상 band 0·1 예산 0 | 2 통과 / 0 실패 |
| 인공 입력 band 255 양수 예산 | 65,541 통과 / 0 실패 |
| 인공 입력 band 255 예산 0 | 1 통과 / 0 실패 |
| 잘못된 expected word·전체 program hash·저장 명령 size 0·분기 대상 | 4개 모두 거부 |
| 원본의 0 예산에 동일한 무처리 복귀 계약 적용 | 정상 band 2개 + 인공 band 1개 모두 descriptor 경계에서 거부 |

band 255는 마스크/주소 산술의 인공 검사이며 실제 지원 band 또는 유효한 hardware table 범위라고 주장하지 않는다. 정상 caller 근거는 band 0·1에 한정한다. 원본 zero의 기대된 거부는 검사기가 baseline 차이를 구분했다는 증거이고 원본 정상 판정이 아니다. 결과는 [GUARD_VERIFICATION.json](GUARD_VERIFICATION.json)에 저장했다.

예산 0에서 후보는 `a0=0`을 반환하고 SP·RA·s0–s11을 복원했다. `9e14`에서 초기화한 스택의 반환 카운터 0을 사용한다. 건너뛴 `9e24`의 스택 slot은 epilogue에서 읽지 않는다. `9ef4`의 global store는 처음 읽은 consumer index와 같은 값을 재저장했다. descriptor 처리 경계 `9e26`, allocator, 소유권 게시와 MMIO 접근은 실행하지 않았다.

양수 비교는 GPR·스택·전역 값·외부 쓰기·읽기 주소·checkpoint PC의 동일성이다. 후보가 명령 한 개를 추가하므로 cycle, instret, interrupt timing의 동일성을 뜻하지 않는다. 예산 0에서도 기존 index/table 읽기는 실행된다.

## Caller와 남은 경계

[기존 실제 binary 조사](../mlo-r36/NPU_TX_BUDGET.md)는 두 직접 caller `0x8400ed8e`와 `0x8400edd8`가 출력 ring free=7에서 `a1=0`을 전달하며 원본은 첫 성공 뒤 예산을 `0xffffffff`로 감소시키는 경로를 확인했다. 두 caller는 반환 `a0`를 사용하지 않는다. 별도 읽기 검토에서 이 경우 반환 후 band1의 `ed92 → ed26`, band0의 `eddc → ede0 → ed6e`로 기존 delay/DMA-index 재읽기 경로가 유지됨도 확인했다. 이 caller 코드는 본 제한 실행기의 대상이 아니며 실제 재개 시간의 보장은 아니다.

본 후보는 알려진 정상 함수 entry에만 적용 가능하다. 미확인 간접 호출, 함수 중간 진입, concurrent reset, 다른 hart의 index 변경을 전범위로 배제하지 않았다. 같은 index 재저장이 동시 reset과 충돌하지 않는다는 증명도 아니다. firmware 전체에는 지원하지 않는 custom opcode와 외부 함수가 있으며 여기서는 실행하지 않는다.

이 guard는 별도 조사된 descriptor READY/stop 계약, completion buffer 소진, mailbox timeout, RRO 삭제 오류, PPE 무효화 문제를 해결하지 않는다. CPU 사용률이 낮고 PPE가 유지된다는 사실만으로 NPU 문제를 배제할 수 없다. 무선 실물 시험이나 Air 원인 귀속은 수행하지 않았다. 수정 blob 공개 허용도 확인되지 않았으므로 이 작업은 로컬 메모리 후보의 제한된 검사로 끝난다.

## 재실행

[기존 이미지 추출·decoder 생성 절차](../mlo-r36/BUILD.md)에 따라 같은 SHA의 program과 decoder JSON을 준비한다. Capstone을 사용할 수 있는 Python 환경이 필요하며, 이 검사기는 의존성을 설치하지 않는다. 이번 실행 환경은 distribution `5.0.9`, module `5.0.7`이었다.

공개 저장소 root에서 다음 명령을 실행한다. `--blob`과 `--instructions`는 필수이며 실제 추출 경로를 넣는다. 후보는 프로세스 메모리에만 존재하고 결과는 JSON stdout으로 출력한다.

```sh
python3 docs/npu-budget-guard-20260926/check_guard.py \
  --blob /path/to/en7581_MT7996_npu_rv32.bin \
  --instructions /path/to/installed-rv32.instructions.json
```

[GUARD_VERIFICATION.json](GUARD_VERIFICATION.json)은 공개 검사기 사본을 r36 추출 program으로 재실행한 결과다. [실행 출처](RUN_VERIFICATION.json)에 코드·입력·결과 hash를 기록했다. 원본과 수정 후보의 실제 firmware 전체 실행은 수행하지 않았다.
