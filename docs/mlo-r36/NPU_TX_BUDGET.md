# NPU TX 처리 예산과 descriptor 대기 경계 후속 검토

분석일: 2026-09-26. 실제 r35 이미지에서 추출한 vendor program과 기존 저장 명령을 읽었다. 실기기 접속·무선 시험·펌웨어 실행·바이너리 변경은 하지 않았다.

본문의 `../npu-firmware-audit-*`, `../mlo-link-transition-*`, `source-cache/`는 공개 저장소에 포함되지 않는 로컬 원본 위치다. 공개 재현에는 [BUILD.md](BUILD.md)의 이미지 추출본과 decoder 생성 절차를 사용한다.

**새 확인 사항:** 출력 ring의 계산된 여유가 정확히 7개이면 TDM RX consumer에 처리 예산 0이 전달된다. consumer는 진입 시 0을 거부하지 않고 처리 후 감소시키므로, 성공 경로에서 예산이 `0xffffffff`로 되감긴다. 정상 최대 128개 제한이 깨지는 산술·제어 흐름은 확인됐지만 실제 장기 정체 발생, 영구 교착, Air 절전 복귀 멈춤과의 인과관계는 미확정이다.

## 입력과 재현 범위

- 입력 program: `../mlo-link-transition-r35-2026-09-26/verified-image/rootfs/lib/firmware/airoha/en7581_MT7996_npu_rv32.bin`
- SHA256: `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643`; 크기 122,336 bytes; 로드 기준 `0x84000000`.
- 저장 디코딩: `../npu-firmware-audit-2026-09-22/installed-rv32.instructions.json`.
- 역할 대조용 FDK: `source-cache/airoha-npu-fdk`, commit `2d13e291ab511b6b319dc5073f47e26cac958ae4`. vendor 원본 C 코드나 동일 빌드가 아니며 최신 버전이라고 표현하지 않는다.

workspace root에서 다음 명령을 실행한다. 원본 입력을 읽고 JSON을 stdout으로 출력한다.

```sh
python3 docs/mlo-r36/check-tx-budget.py --blob "$NPU_PROGRAM" --instructions "$DECODER_JSON"
```

다른 추출본은 `--blob PATH`, 기존 디코딩은 `--instructions PATH`로 지정할 수 있다. 알려진 program hash가 다르거나 선택 구간 bytes가 다르면 검사를 중단한다. 검사 결과는 [tx-budget-verification.json](tx-budget-verification.json)에 보존했다.

| 검사 | 결과 | 의미 |
|---|---:|---|
| program과 저장 명령 대응 | 6구간, 1,153행 일치 | 실행·의미 검증 아님 |
| 표준 RISC-V branch offset의 별도 raw decoding | 26개 일치 | B/JAL/CJ/CB 대상만 검사; vendor custom opcode 제외 |
| hart2 / stop action4 / resume action7 jump table | 3개 일치 | raw signed table offset 계산 |
| 변경된 blob·명령 row 음성 대조 | 2개 거부 | 대응 검사기의 실패 감지 확인 |
| ring 산술 | 3,072개 통과 | 두 ring의 전체 free 범위, producer 0/끝 위치 |
| baseline 예산 속성 | 1,534 통과 / 2 실패, 99.87% | 두 ring 모두 free=7에서 기대된 실패 재현 |
| 0 예산 진입을 생략하는 안전 모델 | 1,536 통과 / 0 실패, 100% | 제안된 산술 조건의 검사; 실제 firmware 수정 아님 |
| 유효 최댓값 다음의 free=count | 2개 거부 | 모델 입력 경계 검사; 원본에 같은 검사 있다는 뜻 아님 |
| stop/timeout 고정 상태 모델 | 16조합 | 7조합이 두 READY 확인 없이 게시 경로에 합류, 그중 5조합은 현재 descriptor도 미준비 |

전체 검사 결과의 `PASS_EXPECTED_BASELINE_FAILURE_REPRODUCED`는 **원본의 기대된 실패를 재현했다는 뜻**이다. baseline firmware가 정상이라는 판정이 아니다. 모델은 descriptor 비트가 관측 사이 변하지 않는 조건을 사용하며, 실기기 메모리·MMIO·동시성·도달 확률·실제 지연 시간을 모사하지 않는다.

별도 읽기 전용 검토에서도 caller, consumer, 8개 batch 게시 경로를 대조했고 검사 재실행 결과가 일치했다. 검토한 `9da4` 함수의 8개 batch 게시 분기에는 예산을 128로 재설정해 zero-budget wrap을 제한하는 경로가 없다. 이 독립 검토 역시 실기기 검증은 아니다.

## 1. 실제 worker와 소유권

`0x84004212`는 `mhartid`를 읽는다. 부트 table `0x8401a2e8`의 index 2는 `0x8400013e`이며, `0013e → 001a0 → ee0a → ec48` 호출로 이어진다. 따라서 검토한 두 band TX loop는 실제 hart2 경로다. 이후 짧은 주소에는 `0x8400` prefix를 붙인다.

Wi-Fi 출력 descriptor의 control bit31이 1이면 NPU가 재사용할 수 있다. `eac6/f350`의 signed-negative 검사가 이 비트를 확인한다. 게시값 `0x004c4048` 또는 `0x40800000`은 bit31을 지워 device로 넘긴다. 이는 host→NPU descriptor의 bit0 DONE 프로토콜과 다른 ring이다.

출력 ring은 band0 512개, 다른 band 1,024개다. 다음 위치는 각각 `&0x1ff`, `&0x3ff`로 wrap한다. 현재 위치와 바로 다음 위치를 모두 확인한다. 실제 callback은 각각 slow `e87a`, fast `f1ea`다. fast는 TDM consumer `9da4`에서 호출되며 기존 source의 다른 직접 호출점도 있어, 이 문서의 예산 도달 증명은 **ec48 → 9da4 경로**에 한정한다.

## 2. free=6은 생략하지만 free=7은 0 예산으로 호출한다

worker는 producer P, 저장 DMA index D, ring 크기 N에 대해 다음을 계산한다.

```text
free = D - P - 1          (P < D)
       D + N - P - 1      (P >= D)
```

한 칸을 보존하므로 유효 산술 범위는 `0..N-1`이다. DMA index는 loop의 일부 지점에서 갱신하므로 이 계산이 실시간 여유와 항상 일치한다는 보장은 별개다.

| 단계 | band1 | band0 | 동작 |
|---|---|---|---|
| 초기 검사 | `ed14` | `ed5c` | `s1=5`; free≤5이면 호출 생략 |
| slow 한 개를 위한 예약 | `ed18` | `ed60` | `s0=free−1`; 실제 slow가 소비했는지와 무관 |
| 추가 검사 | `ed22` | `ed6a` | `s0==5`, 즉 free=6이면 TDM 호출 생략 |
| 전달 예산 | `ed88` | `edd2` | `a1=s0−6=free−7` |
| TDM consumer 호출 | `ed8e` | `edd8` | 둘 다 `9da4` |

따라서 free=6에서 음수/unsigned underflow 인자를 넘기는 경로는 없다. 문제는 **free=7**이다. 예를 들어 N=512, P=504, D=0이면 free=7이다. 이는 유효 index 조합이며 단일 producer의 ring 산술만으로 배제되지 않는다. 실제 관측됐다는 뜻은 아니다.

consumer `9da4`는 `9dc2`에서 예산을 128로 초기화하고, `9dec`에서 인자가 127보다 큰 경우에만 그 값을 유지한다. 0은 `9df0`에서 그대로 저장된다. `9e26`의 첫 descriptor 처리 전 zero guard는 없다. 한 패킷의 성공 처리가 끝나면 `9ed8 → 9eda → 9edc`에서 예산을 읽고 1을 빼 저장한다. `9ede`는 남은 값이 0이 아니면 `9e26`으로 돌아간다.

```text
free=7 → argument=0 → first successful packet → remaining=0xffffffff
128 successes later → remaining=0xffffff80, still nonzero
```

다른 exit가 전혀 없다고 놓은 32비트 산술에서는 2^32회 감소해야 0이 된다. 실제로 그 횟수만큼 연속 실행됐다는 증거는 아니다. 단일 소비 회차가 정상 128개 제한을 넘어 다른 band 처리와 바깥 readiness 검사로의 복귀를 지연시킬 수 있다는 조건부 영향이다.

## 3. 무조건 무한 실행으로 해석하면 안 되는 이유

다음 경로가 먼저 실행될 수 있다.

- RX descriptor에 입력이 없으면 `9e32 → 9fa4`를 거쳐 부분 batch 처리 후 반환한다.
- replacement token 할당 실패는 `9e7a → 9f18`로 간다. 실패 표식 `s8=1`에 의해 `9ed4 → 9ee0`으로 예산 감소 경로를 벗어난다.
- TX forward가 `-1`을 반환하면 `9ebe → 9f66`에서 원래 token을 반환하고 실패 회차를 정리한다.
- TX forward 내부의 출력 descriptor 대기는 별도다. READY가 올라오거나 stop flag가 설정되면 대기를 벗어나며, 다음 descriptor 대기 자체에는 횟수 제한이 없다. 반대로 hardware가 진행하지 않으면 caller의 예산 검사로 돌아오지 못한다.
- 정상 예산이 양수인 경우에는 예산 소진으로 반환한다. 입력이 계속 준비돼 있고 할당/전송도 성공할 때에만 zero 예산 wrap의 장기 drain 영향이 드러난다.

8개 처리마다 `9f54/9f58`, 마지막 부분 묶음은 `9f8c/9f9e` 등에서 RX/TX CPU index를 게시한다. 이 게시 경로가 있어, batch를 묶는다는 사실만으로 consumer가 자기 미게시 descriptor를 기다리는 순환 교착을 입증할 수는 없다. 정상 index/소유권/단일 producer 불변식과 DMA 진행이 유지되면 여유 확인과 reserve는 backpressure를 완화한다. **free=7 예산 오류는 이 불변식 검토와 별도로 존재한다.**

## 4. stop과 현재 descriptor timeout은 취소 반환이 아니다

slow 현재 descriptor의 READY 성공(`e9be`), 1000회 소진(`e9c2`), stop(`e9ce`)은 모두 `ea78`에 합류한다. 다음 descriptor의 READY(`eac6`)와 stop(`ead2`)은 모두 `eb10`에 합류한다. 이후 `eb7e/eb82`에서 현재 descriptor의 주소/control을 쓴다.

fast도 현재 READY(`f28e`), 소진(`f292`), stop(`f29e`)이 `f30a`에 합류한다. 다음 READY(`f350`)와 stop(`f35c`)이 `f386`에 합류하고, 이후 `f3e8/f3ee`에서 현재 descriptor를 게시한다. 따라서 stop을 “실패 반환으로 안전하게 빠져나감”으로 해석하면 안 된다.

실제 control action table `0x8401bd64`의 action4는 `e220`이며 stop byte `0x3e9046f5`를 1로 쓴 다음 config 상태들을 내린다. action7은 `e0c0`에서 stop을 지우고 상태를 재개한다. 이 분기 사실만으로 외부 장치의 정지/드레인 순서까지 알 수는 없다. stop 시 게시가 coordinated shutdown에서 허용되는지, 잘못된 소유권 덮어쓰기가 실제 가능한지는 추가 계약 확인이 필요하다.

## 5. FDK와 차이 및 안전한 복귀의 필요조건

FDK `tx_fast_path_runtime.c:168`은 free>7일 때만 TDM을 호출하므로 free=7을 배제한다. `tdm_tx_forward.c:119–147`, `tx_packet_slow_path.c:155–190`의 대기 helper는 종료 뒤 READY를 다시 검사하고 false/FULL을 반환한다. 이는 실제 vendor 분기와 다른 동작이며 FDK에 해당 방어가 있다는 이유로 vendor firmware도 안전하다고 볼 수 없다.

시간 제한만 넣는 binary patch는 제안하지 않는다. fast caller는 dispatch 전에 replacement buffer를 RX descriptor에 쓰고(`9e9e`), RX 소유권을 넘긴다(`9eaa`). 안전한 실패에는 최소 다음 조건이 필요하다.

1. 현재 출력 descriptor/record를 게시하기 전에 실패를 판정하고, producer를 진행시키지 않는다.
2. 이미 RX 입력에서 분리한 원래 token은 기존 `-1` cleanup 경로(`9f66 → 4b96`)로 반환한다. 단순 worker 탈출은 누수/소유권 손실 위험이 있다.
3. 앞서 성공한 부분 batch의 RX/TX CPU index 게시를 완료하고 소비 index를 보존한다.
4. slow 입력은 재시도 가능한 경우 입력 소유권과 producer를 보존한다. 현재 blob의 stop 분기는 이 계약을 제공하지 않는다.
5. stop은 장치 quiesce/restart 계약과 맞춰 처리한다. index/소유권 불일치가 지속되면 timeout만으로 장치가 복구되는 것은 아니다.

예산 0을 생략하는 모델은 위 전체 복구 계약을 구현하거나 검증한 것이 아니다. 추가 실기기 시험은 수행하지 않았으며, 이 보고서는 Air 원인 확정·NPU firmware 수정 완료·안정성 해결을 주장하지 않는다.
