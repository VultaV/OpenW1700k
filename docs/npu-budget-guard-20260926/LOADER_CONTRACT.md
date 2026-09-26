# NPU firmware 로더·무결성·배포 계약 기록

2026-09-26. 현재 r36의 로컬 소스·추출 이미지·기존 decoder를 읽고 확인했다. 이 작업 흐름의 산출물은 **메모리 안의 guard 검증 코드와 분석**에 한정한다. 이 기록 작성에서는 수정 blob을 생성·포장·배포·설치하지 않았고, 장비 접속·재부팅·새 네트워크/무선 시험도 하지 않았다. r36 릴리스는 변경하지 않았다.

핵심은 **호스트 로더가 NPU 전용 서명·체크섬을 검사하지 않는다는 관측과, 수정 firmware의 부팅 성공·수정 재배포 허락은 서로 다른 문제**라는 점이다. 후자의 두 항목은 여기서 확인되지 않았다.

## 입력과 라이선스 원문

입력 21개의 상대 경로·크기·SHA256·소스 행 기준은 [LOADER_INPUTS.json](LOADER_INPUTS.json)에 보존했다. 이후 소스가 바뀌면 행 번호보다 해당 해시를 기준으로 구분해야 한다.

| 입력 | 크기 | SHA256 |
|---|---:|---|
| MT7996 program | 122336 bytes | `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643` |
| MT7996 data | 3084 bytes | `61a75afb052feed2ceb2f3023e16f50317c05c78f9c8e564bf01924ce39c7ec1` |
| LICENSES/LICENSE.airoha | 556 bytes | `ad548ca0ffb91ec655de0f28e13089ef1cd4e0deabb2f15a9289194990e62252` |
| 실제 prepared airoha_npu.c | 입력 JSON 참고 | `e001cd6e345db45d6d69eee7a68e26a3a04bcdda090ca96b8f4a58162581c62c` |

linux-firmware `20260810`의 `LICENSES/LICENSE.airoha:1–5`에는 **“permission to use and redistribute”**가 적혀 있다. Airoha chipset 장치용 사용·재배포를 대상으로 하고, firmware 자체에 GPL/LGPL을 적용해야 하는 형태를 제외한다. `WHENCE:2085–2091`이 `en7581_MT7996_npu_rv32.bin`과 `en7581_MT7996_npu_data.bin`을 이 라이선스에 연결한다.

이 원문에는 modification/derivative 허락이 명시돼 있지 않다. **수정 재배포 허락을 확인한 것이 아니며, 금지라고 법률 판단한 것도 아니다.** GPL인 호스트 driver나 MIT인 FDK의 라이선스를 vendor blob의 수정 허락으로 사용할 근거도 이 기록에는 없다. 원문 실제 위치는 JSON의 `license` 입력이며, 현재 source tree에서 최상위 `LICENSE.airoha`가 아니라 `LICENSES/LICENSE.airoha`에 있다.

## 소스 다운로드·패키지·이미지 계약

`package/firmware/linux-firmware/Makefile:10–16`은 `linux-firmware-20260810.tar.xz`, release 1, archive SHA `ac17c34fe73756926a961fbafadf8d8f07a3bd2dd2f4ea31a0fb5d50c714a49a`를 지정한다. 이번에는 archive 자체를 다시 다운로드하거나 해시 계산하지 않았다.

`airoha.mk:32–39`는 MT7996 두 파일을 `/lib/firmware/airoha`로 그대로 복사한다. 이 recipe에는 NPU 전용 compile·header 작성·checksum 재작성·서명 단계가 없다. r36 추출 rootfs의 설치 package는 `airoha-en7581-mt7996-npu-firmware 20260810-r1`이고, source program/data와 r36 rootfs의 두 파일은 각각 byte와 SHA가 동일하다.

이 source archive hash와 전체 sysupgrade FIT/rootfs hash는 외부 전달·포장의 무결성 경계다. NPU가 로드된 코드를 인증하거나 그 코드가 정상 실행됨을 증명하는 값은 아니다. 향후 별도로 허용된 firmware package를 만들더라도 현재 r36의 불변 firmware 검사를 완화해 기존 결과를 그대로 재사용해서는 안 된다.

## 호스트 로더가 실제로 검사하는 것

prepared `airoha_npu.c:225–247`의 순서는 `request_firmware_direct()` → 크기 상한 검사 → `memcpy_toio()` → `release_firmware()`다. NPU 전용 header/magic·CRC/hash·signature·entry parsing·relocation·version/ABI 호환 검사 없이 파일 전체를 복사한다.

- Program 상한: `0x200000` = 2 MiB. Data 상한: `0x10000` = 64 KiB (`:24–25`). 상한 안에 든다는 것만으로 실제 firmware 내부 layout이 안전하다는 뜻은 아니다.
- 일반 file loader는 nonempty regular file과 full read를 검사한다 (`fs/kernel_read_file.c:48–74,104–110`). 따라서 NPU driver에 별도 최소 크기 검사가 없더라도 일반 filesystem 경로는 빈 파일을 받아들이지 않는다.
- 현재 kernel 설정은 `SECURITY=n`, `EXTRA_FIRMWARE=""`, `FW_LOADER_COMPRESS=n`이다. 이 구성에서 `security.h:1307–1318`의 read hooks는 0을 반환한다. 검토한 현재 host 경로에서 firmware authentication은 발견하지 못했다.
- `request_firmware_direct()`는 userspace sysfs fallback을 생략한다. `-ENOENT`는 NPU driver가 `-EPROBE_DEFER`로 바꾼다. 파일이 없는 경우와 잘못된 코드가 복사된 경우는 다른 실패 경로다.

실제 r36 DTB를 로컬 파싱해 두 `firmware-name`의 순서가 **program → data**임을 확인했다. `an7581-npu-mt7996.dtsi:5–7`과 일치한다. 첫 reserved-memory의 base는 `0x84000000`, 크기는 `0xa00000`이다. `airoha_npu.c:263–270`은 program을 이 DRAM resource에, data를 NPU mapping의 local SRAM offset 0에 복사한다.

같은 파일 `:849–856`은 8개 core의 boot base를 모두 `res.start`로 설정하고 boot config `0xff`, trigger `1`을 쓴다. 파일 header에서 entry를 얻지 않는다. program 시작은 저장 decoder상 `c.nop`이며 offset `0x10`은 `fence.i`다. 이 관측을 전체 firmware 재디코딩이나 내부 self-check 부재 증명으로 해석하지 않는다.

## 부팅 판정과 hot reload의 한계

**`:859–866`은 firmware version mailbox가 실패해도 probe에서 최종 0을 반환한다.** 드라이버 bound 상태나 오류 로그 부재는 firmware 부팅 성공을 증명하지 않는다. 버전 값도 수정 코드의 특정 실행 경로가 정상임을 대신하지 못한다.

이 platform driver에는 `.remove`, `.shutdown` 또는 coordinated reset/reload callback이 없다. filesystem의 blob을 바꿔도 이미 실행 중인 NPU가 교체되지 않으며, module unbind/rebind를 안전한 hot reload로 간주할 근거가 없다. 이 기록에서는 해당 동작을 수행하지 않았다.

일반 firmware loader의 검색 우선순위는 사용자 지정 `firmware_class.path`, `updates/<kernel-release>`, `updates`, `<kernel-release>`, 기본 `/lib/firmware` 순이다 (`drivers/base/firmware_loader/main.c:472–477`). 기본 경로의 파일 SHA만 확인해서 실제 로드된 파일을 단정하면 안 된다. 파일 교체 후의 loaded-image identity와 재시작 절차는 별도의 검증 대상이다.

## 확정하지 못한 조건

호스트 copy 경로에 검사가 없다는 사실로 **blob 내부 checksum/self-check, signature 필드, ROM 또는 하드웨어 authentication이 없다고 증명할 수 없다.** 전체 startup CFG와 ROM 동작은 복원하지 않았다. 관련 문자열이 발견되지 않았다는 관측도 부재 증명으로 사용하지 않았다.

수정 code의 실제 부팅·NPU 기능·유선 지속성·Air 절전 복귀 멈춤 해결은 모두 미검증이다. 메모리 안의 산술 guard 검증이 통과해도 firmware 수정·실행·배포 완료로 기록하지 않는다.

## 향후 기술 검증 전제

1. 정확한 원본 program SHA와 변경 위치의 old bytes를 먼저 검사하고, candidate hash·변경 주소·명령 효과를 별도로 기록한다. 최소 길이 보존 변경도 의미·동시성 안전성 증명은 아니다.
2. Program/data pairing, board가 선택하는 이름, load/entry·고정 data·stack layout을 보존한다. branch/register, ownership/token 정리, 부분 batch/index 게시, 다른 caller와 실패 경계를 함께 검증한다.
3. 미래의 별도 허용된 package 작업에서는 firmware package 개정을 구분하고 deterministic 변환을 기록한다. 최종 APK/rootfs에서 candidate bytes를 다시 확인하고 외부 FIT/image hash도 재생성·검증한다.
4. 복구 가능한 접근 경로와 원본 firmware를 확보한 별도 승인된 부팅에서 응답·core/IRQ/DMA/flow 진행을 검증해야 부팅·기능 성공을 말할 수 있다. 지금 수행한 작업이 아니다.
5. 사용자의 추가 무선 시험 중지 조건을 유지한다. 현재 정적·host 검증은 Air 실기기 수락 시험을 대신하지 않는다.

이 목록은 기술적 전제와 미확인 범위를 적은 것으로, vendor firmware 수정·포장·배포·설치·실행을 승인하거나 라이선스 결론을 내리는 문서가 아니다.
