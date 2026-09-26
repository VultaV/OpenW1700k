# NPU 바이너리 후속 대조 — 2026-09-26

Clanker errata E2/E3를 현재 vendor NPU의 확인된 결함으로 귀속할 근거는 없다. 이번에 주소까지 좁힌 대응 경로는 링 구조와 buffer pool 사용 방식이 다르다. 이것은 현재 NPU 전체의 무결함이나 정상 실행을 증명하지 않는다. 공유기는 r32이고 r34는 설치하지 않았으며, 추가 무선 시험은 하지 않았다.

## 비교 대상과 재현 범위

- Vendor program: `en7581_MT7996_npu_rv32.bin`, 122,336 bytes, SHA256 `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643`.
- Vendor data: 3,084 bytes, SHA256 `61a75afb052feed2ceb2f3023e16f50317c05c78f9c8e564bf01924ce39c7ec1`. 두 파일은 기존 분석본과 현재 staged 파일이 동일하다. 아래 checker는 program만 검사한다.
- Program load base `0x84000000`; `0x8401c778`의 문자열은 `TLB7.7.0.0_v03`이다. Clanker 소스의 `TLB7.8.0.0_v003`를 이 파일의 버전으로 읽으면 안 된다.
- 원본 배포 근거: [linux-firmware의 해당 파일](https://gitlab.com/kernel-firmware/linux-firmware/-/blob/797d34e622b2262ca0777e98fd40b1d29034169d/airoha/en7581_MT7996_npu_rv32.bin). 비교한 재구현은 [ClankerNPU `6d0cd8ae`](https://github.com/ClankerConstruction/ClankerNPU/tree/6d0cd8ae9f6f324a82faa68352624f7cbc237e37)이다.

기존 `artifacts/npu-firmware-audit-2026-09-22/installed-rv32.instructions.json`은 Capstone RV32+compressed 선형 디코딩 결과다. 아래 범위의 각 행 주소·길이·바이트를 실제 blob에 다시 대조했다. 데이터나 vendor 명령을 잘못 디코딩할 가능성 때문에 바이트 일치를 의미 해석의 증명으로 세지 않는다.

| 범위 `[시작, 끝)` | 저장된 decoder 행 수 |
|---|---:|
| `0x840091b4–0x840093d4` TDMA 제출 | 179 |
| `0x84004d0e–0x84004e1c` software pool 반환·할당 | 92 |
| `0x840064b4–0x8400655c` hardware mutex helper | 63 |
| `0x8400aedc–0x8400b074` TDMA caller | 140 |
| `0x8400cb1a–0x8400cd1a` indication worker | 162 |
| `0x8400e084–0x8400e292` RRO action dispatch | 171 |
| 합계 | **807** |

E2/E3용 원래 다섯 구간은 636행이고 RRO 구간은 별도 171행이다. 범위 밖 raw byte anchor 세 곳도 확인한다. [검사 스크립트](../../tests/check_npu_firmware_paths.py)는 Python 표준 라이브러리만 사용하고 입력 파일을 수정하지 않는다.

```sh
python3 tests/check_npu_firmware_paths.py /path/to/en7581_MT7996_npu_rv32.bin /path/to/installed-rv32.instructions.json
```

로컬 artifact가 없는 공개 checkout에서는 위 linux-firmware 고정 commit의
program 파일을 받아 다음과 같이 decoder JSON을 생성할 수 있다. 기존 분석의
distribution은 `capstone==5.0.9`, 모듈이 보고한 decoder 버전은 `5.0.7`이었다.
아래는 기존 생성기의 program 디코딩 부분이며, 새 환경에서 실행한 결과로
주장하지 않는다. checker 자체에는 Capstone이 필요 없다.

```sh
python3 -m venv .venv-npu-audit
.venv-npu-audit/bin/python -m pip install 'capstone==5.0.9'
.venv-npu-audit/bin/python - /path/to/en7581_MT7996_npu_rv32.bin installed-rv32.instructions.json <<'PY'
from pathlib import Path
import hashlib, importlib.metadata, json, sys
import capstone
blob = Path(sys.argv[1]).read_bytes()
assert hashlib.sha256(blob).hexdigest() == 'e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643'
assert importlib.metadata.version('capstone') == '5.0.9'
assert capstone.__version__ == '5.0.7'
md = capstone.Cs(capstone.CS_ARCH_RISCV, capstone.CS_MODE_RISCV32 | capstone.CS_MODE_RISCVC)
md.skipdata = True
rows = [dict(address=i.address, size=i.size, bytes=i.bytes.hex(), mnemonic=i.mnemonic, operands=i.op_str)
        for i in md.disasm(blob, 0x84000000)]
assert len(rows) == 44253 and sum(row['size'] for row in rows) == len(blob)
Path(sys.argv[2]).write_text(json.dumps(rows) + '\n')
PY
python3 tests/check_npu_firmware_paths.py /path/to/en7581_MT7996_npu_rv32.bin installed-rv32.instructions.json
```

검사 결과: 정상 입력 1회 통과(807행·raw anchor 3곳), 잘못된 firmware hash·변조된 decoder byte·누락 행·비연속 주소의 음성 대조 4건 모두 예상대로 거부됐다. 예기치 않은 실패와 skip은 0건이다. 음성 대조는 검사 스크립트의 입력 검증이며 실기기 회귀 시험 수로 합산하지 않는다.

원시 펌웨어·설정 백업·패킷·단말 식별자는 이 기록에 포함하지 않았다.

## E2: TDMA ring full 시 mutex 미해제 주장

[Clanker errata E2](https://github.com/ClankerConstruction/ClankerNPU/blob/6d0cd8ae9f6f324a82faa68352624f7cbc237e37/docs/errata.md)는 kite pipeline의 `tdma_tx_submit`이 mutex 0을 잡은 채 포기한다고 설명한다. [현재 재구현](https://github.com/ClankerConstruction/ClankerNPU/blob/6d0cd8ae9f6f324a82faa68352624f7cbc237e37/npu_tdma.c)은 1024개×8바이트 링과 kite mutex 0을 사용한다.

실제 blob의 대응 TDMA 제출 함수는 다음과 다르다.

- `0x840091e0`의 `addi a7, zero, 0x7ff`와 `0x840092c4`의 `slli a5, s0, 5`: 2048개×32바이트 descriptor.
- `0x840091ee`는 재시도 횟수 5를 설정한다. `0x84009242–0x8400926e`는 횟수를 소진하면 `-1`로 반환한다. 이 경로에서는 함수 진입 후 mutex 획득 호출이나 mutex MMIO 쓰기가 없다.
- 직접 확인한 호출 지점은 `0x8400af7c`, `0x8400ccc4`이다. 함수 내 다른 두 호출은 padding 경로와 오류 출력 경로다.

따라서 이 함수가 E2와 같은 방식으로 자신이 잡은 mutex를 누락한다고 해석할 수 없다. **함수 구조 대조의 확신도는 높다.** 다만 모든 상위 caller, 간접 호출 및 별도 hart의 mutex 소유 관계를 복원한 것은 아니므로 NPU 전체의 lock 문제를 배제하지 않는다.

## E3: 잘못된 software pool 반환 주장

[Clanker의 kite pipeline worker](https://github.com/ClankerConstruction/ClankerNPU/blob/6d0cd8ae9f6f324a82faa68352624f7cbc237e37/npu_wifi_rx.c)는 3200개×8바이트 handoff에서 classifier/forwarding 실패 후 buffer manager로 돌려준다. E3의 전제는 해당 pipeline이 software pool에서는 할당하지 않는다는 것이다.

실제 blob에서 확인한 대응 경로는 software pool을 사용한다.

- 반환 함수 `0x84004d0e`: `gp+0x7e0`에서 pool 주소를 읽고 `0x84004d44`에서 16비트 ID를 저장한다.
- 할당 함수 `0x84004d80`: 같은 `gp+0x7e0`를 읽어 `0x84004dea`에서 16비트 ID를 가져온다.
- RX 초기화의 `0x8400b766`, `0x8400b894`와 refill의 `0x8400beb4`가 이 allocator를 호출한다.
- `0x8400ccc4`의 TDMA 제출 실패는 `0x8400ccce → 0x84004d0e`로 반환한다. 이 worker의 진단 문자열은 `eagle_handle_ind_cmd_ring_part2`이며 handoff는 2048개×16바이트다.

이 대응 경로에는 E3의 “사용하지 않는 software pool로 반환” 전제가 맞지 않는다. **동일 pool의 할당·반환 확인은 높은 확신도, E3 원본과의 완전한 대응은 미확정**이다. 코드명 kite/eagle이나 MT7996 이름만으로 두 구현을 같다고 판단하지 않는다.

## RRO action 3의 실제 범위

`0x8401bd70`의 원문 바이트 `62 24 ff ff`는 signed LE offset `-56222`다. jump table base `0x8401bd64`를 더하면 action 3 진입점 `0x8400e1c6`이 된다.

- `0x8400e1ea`: `addi a2, zero, 0x400` — 특수 selector는 **1024**다.
- `0x8400e1fc`: selector 비교 후 일반/special table 경로를 고른다.
- `0x8400e20c`: `sb a1, 7(a4)` — `a1=-1`의 하위 바이트 `0xff`를 기록하며 1024개 descriptor의 signature를 무효화한다. 이 동작을 메모리 해제라고 부르면 안 된다.
- wrapper `0x8400fc3e`의 원문 `ef e0 6f c4`는 dispatch 호출이며, `0x8400fc44`의 `05 45`는 `c.li a0, 1`이다. 이 상수 응답만으로 NPU/WM 전체 reset 완료를 보증할 수 없다.

호스트 mt7996의 기존 `init.c` 경계에서 NPU 삭제 반환값(`1188`), WM reset 반환값(`1214`)을 무시하고 이벤트 항목을 해제(`1216`)하는 사실은 별도 호스트 코드 검토 결과다. WM 실패는 음수 오류뿐 아니라 0이 아닌 firmware status도 포함한다. MCU timeout에는 recovery work가 있으므로 “복구가 전혀 없다”는 결론도 부정확하다. timeout 뒤 이전 요청의 실행 여부와 session 재사용 순서가 미확정이어서 무조건 retry의 안전성은 입증되지 않았다. 이 checker는 호스트 코드나 재시도 안전성을 검사하지 않는다.

## 원인 판단의 한계

Clanker E2/E3 설명에는 원본 vendor 파일명·SHA256·함수 PC·명령 시퀀스가 없다. 우선 그 원본을 확보해 같은 바이너리와 모드인지 대응시켜야 한다. 현재 관측한 Air 멈춤과 연결하려면 해당 경로 실행, mutex 소유 또는 pool 고갈의 동시 증거가 추가로 필요하다. **CPU가 낮고 PPE가 유지됐다는 사실만으로 NPU 문제를 배제할 수 없다.** 현재 E2/E3의 Air 증상 원인 귀속 확신도는 낮다.

기존에 확인한 무제한 next-TX-descriptor 대기와 TXdone의 replacement 할당 선행은 별개의 조건부 경로다. 이번 E2/E3 대조로 해소되거나 실기기 원인으로 입증된 것이 아니다.
