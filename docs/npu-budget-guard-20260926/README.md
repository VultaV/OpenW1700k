# NPU zero-budget guard — 분석 후보, 설치 이미지 아님

2026-09-26의 r36 후속 조사다. **이 디렉터리는 실제 vendor 프로그램의 4-byte guard 후보를 메모리 안에서 검사한 코드와 근거이며, 수정한 firmware blob이나 새 r 버전 이미지가 아니다.** 원본 파일·빌드 입력·공유기·r36 태그와 릴리스는 변경하지 않았다. 추가 무선 시험도 하지 않았다.

## 겨냥하는 오류와 최소 변경

[r36 분석](../mlo-r36/NPU_TX_BUDGET.md)에서 출력 ring 여유가 정확히7일 때 fast consumer에 budget0이 전달되고, 첫 성공 처리 뒤 `0xffffffff`로 되감기는 경계를 확인했다. 이는 예산128의 정상 상한을 우회하지만 실제 Air 멈춤의 원인인지는 미확정이다.

SHA256 `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643`의 122336-byte program에서만 다음 후보를 검토한다. 주소는 load base `0x84000000` 기준이다.

| 주소 | 원본 | 후보 |
|---|---|---|
| `0x84009e1a` | `andi s1,a0,0xff` (4 bytes) | `c.mv s1,s8` (2 bytes) |
| `0x84009e1c` | 위 원본 instruction의 뒤쪽 절반 | `c.beqz a1,0x84009ee4` (2 bytes) |

바이트는 `9374f50f` → `e284e1c5`다. 바로 앞에서 이미 계산한 `s8=a0&0xff`를 재사용한다. 길이와 이후 주소는 바뀌지 않는다. 양수 budget에서는 새 분기를 통과해 원본과 같은 검사 대상 레지스터·메모리 상태로 합류하고, 0은 초기화가 끝난 기존 epilogue로 반환한다.

이것은 실제 실행 중인 instruction 메모리를 덮어쓰는 hot patch가 아니다. 검사기는 디스크 원본을 읽어 메모리 복사본만 비교하며 수정 blob을 저장하지 않는다. raw bit field와 새 Capstone 해석이 일치했다. Apple clang의 RV32 assembler는 지원 오류로 실패했으므로 assembler 검증 성공으로 기록하지 않았다. [RISC-V C 명령 규격](https://docs.riscv.org/reference/isa/v20260120/unpriv/c-st-ext.html)에 정의된 register copy와 zero branch 형식을 사용한다.

## 보존되는 계약과 남는 경계

정상 함수 entry와 확인된 band0/1 caller를 기준으로 한다. budget0은 RX descriptor 접근·token 할당·소유권 반환 전에 return0으로 빠지고 SP·RA·callee-saved 레지스터를 복원한다. epilogue는 기존 consumer index를 RAM에 같은 값으로 한 번 다시 저장한다. 따라서 **소비·소유권의 진행이 없다는 뜻이며 공유 메모리 쓰기가 전혀 없다는 뜻은 아니다.** 비동기 reset이나 알려지지 않은 중간 진입까지 안전함을 증명하지 않았다.

caller의 threshold를5에서6으로 바꾸는 대안은 free6에서 기존 slow 처리를 없애므로 사용하지 않았다. 이 후보는 caller를 바꾸지 않아 free6 처리를 보존하며, free7 반환 뒤 두 caller가 기존 delay와 DMA index 재조회로 진행한다. 양수 경로에 명령 하나가 추가되므로 cycle·instruction-retirement counter·interrupt timing의 동일성을 주장하지 않는다. 시간에 따른 MMIO 진행이나 무선 처리 공정성을 검증한 것도 아니다.

- [명령 수준 검증 설계](GUARD_DESIGN.md), [실행 결과](GUARD_VERIFICATION.json)
- [raw encoding·새 decoder 대조](ENCODING_VERIFICATION.json)
- [실제 로더·패키지·배포 계약](LOADER_CONTRACT.md)

이번 결과는 부팅·하드웨어 인증·전체 firmware CFG·동시성·실기기 안정성 또는 Air 멈춤 해결 판정이 아니다. 다음 배포 판단에는 이 문서의 한계를 넘는 근거가 필요하다. r36의 host TX barrier 수정과 이 NPU 내부 후보를 구분해야 한다.
