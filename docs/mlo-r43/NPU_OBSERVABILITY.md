# r43 zero-budget 가드의 실행 중 관측 한계

2026-09-27. 저장된 펌웨어 디코딩·호스트 소스·기존 검증 문서의 읽기 전용 검토다. 장치 조회, 설정 변경, 추가 시험은 하지 않았다. 아래 경로는 작업 폴더 기준 상대경로이며 줄번호는 이번 검토 시점 기준이다.

**결론: 고정된 r43 펌웨어와 기존 읽기 값만으로 zero-budget 가드의 호출 횟수 또는 저하·멈춤과의 인과를 확정할 수 없다. 큐 압력과 일부 처리 단계의 진행 여부는 보조 증거가 된다.**

## 확인한 사실

- **고유한 가드 실행 흔적이 없다.** `0x84009e1c`의 zero 분기는 기존 epilogue `0x84009ee4`로 간다. 반환값은 0이며, `0x84009ef4`는 처음 읽은 consumer index를 같은 값으로 재저장한다. 양수 예산의 입력 없음 경로도 같은 저장을 수행한다. 두 직접 caller는 반환값을 사용하지 않는다. 따라서 index 불변이나 반환값으로 가드 실행을 구분할 수 없다.
  - `publish-mlo-r29/docs/npu-budget-guard-20260926/GUARD_DESIGN.md:43–49`
  - `publish-mlo-r29/docs/npu-budget-guard-20260926/CONCURRENCY_REVIEW.md:20–38`
  - `artifacts/npu-firmware-audit-2026-09-22/installed-rv32.linear-disassembly.txt:14107–14114`

- **free 계산은 현재 DMA index가 아닌 cached D를 사용한다.** band 1/0의 producer P는 각각 펌웨어 주소 `0x3e9021f4` / `0x3e903978`에서 읽는다. D는 worker stack `+0xa` / `+8`에 보관된다. register-pointer globals `0x3e9046fc` / `0x3e904700`을 경유해 `regs+0xc`를 읽은 뒤 D를 갱신하는 경로에는 1,000회 delay loop가 있다. host가 현재 P/D를 순차 조회한 값은 호출 시점의 `free=7 → a1=0`과 같다고 보장되지 않는다. 이 주소들은 펌웨어 주소이며 검증 없이 host 물리주소로 사용하면 안 된다.
  - `artifacts/npu-firmware-audit-2026-09-22/installed-rv32.linear-disassembly.txt:20752–20830` 및 `20853–20857`
  - `publish-mlo-r29/docs/mlo-r36/NPU_TX_BUDGET.md:50–75`

- **기존 출력은 다른 단계의 상태다.** token/host queue head-tail, 무선 하드웨어 큐, PPE byte 증가는 점유·일부 진행의 증거다. 이 값은 위 cached D나 branch-hit 횟수가 아니다. 호스트 ABI에 `GET_COUNTER`·`GET_DBG_COUNTER` 이름은 있지만, 검사한 호스트 경로에서 zero-budget 전용 필드·조회 계약은 확인되지 않았다. 개발킷의 `output_capacity_limit_count`를 설치된 vendor 바이너리의 카운터로 간주할 수 없다.
  - `build-volume/source/build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/mt76-2026.09.01~01367e60/mt7996/debugfs.c:739–815,952–1011`
  - `build-volume/source/build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.44/include/linux/soc/airoha/airoha_offload.h:152–164`
  - `source-cache/airoha-npu-fdk/src/an7581/services/wifi/tx_fast_path_runtime.c:148–169`

- **기존 WDT 진단은 PC/SP/LR을 읽는다.** 공유 epilogue PC만으로 zero 분기를 구분할 수 없다. 실행 중 PC·SP·stack을 따로 읽은 값도 하나의 원자적 실행 상태가 아니다.
  - `artifacts/npu-zero-budget-r43-2026-09-27/airoha_npu.candidate.c:388–408`

## 미확정 및 가능한 범위

시간을 맞춘 큐·token·PPE·TCP 자료는 입력 부족, 출력 압력, 일부 단계의 정체 여부를 좁히는 데 사용할 수 있다. 그러나 순차 snapshot과 누적 전송량으로 **가드 호출 빈도, 호출 당시 cached free, 해당 분기의 체류시간**을 복원할 수는 없다. PC 샘플 하나도 경로 전체의 빈도·시간을 증명하지 않는다.

새 카운터에 사용할 SRAM/DRAM 주소의 미사용 여부·소유권·초기화 수명이 검증되지 않았다. 안전한 공간이 절대 없다는 뜻이 아니라, 현재 자료로 안전하다고 지정할 수 있는 공간이 없다는 뜻이다. 빈 영역처럼 보이는 위치를 임의로 쓰거나, 관측을 위해 NPU STOP·reset·halt를 수행하는 방안은 제안하지 않는다. 기존 가드의 정적 검증이나 정상 회차만으로 원래 멈춤의 해결을 주장하지 않는다.
