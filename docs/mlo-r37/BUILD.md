# r37 빌드·검증 재현

기존 [고정 toolchain/feed/overlay 절차](../mlo-r34/BUILD.md)를 사용하되 r37 source tag, `r37.config`, `build-manifest.json`을 적용한다. NPU host module package는 `6.18.44-r3`이며 mt76은 `r29`, kernel release는 `6.18.44-w1700k-mlo-r32`를 유지한다. 개인 백업이나 Tailscale 상태를 이미지에 복사하지 않는다.

`BUILD_RESULT.json`에 기록된 9개 make 명령을 모두 실행한다. 저장된 성공 기록을 이유로 dependency 검사를 생략하지 않는다. 완료 후 다음 검사로 prepared source와 최종 이미지를 대조한다.

```sh
python3 tests/test_airoha_npu_mailbox.py --source "$KERNEL/drivers/net/ethernet/airoha/airoha_npu.c"
python3 docs/mlo-r37/verify-image.py BUILD IMAGE NEW_OUTPUT \
  docs/mlo-r37/build-manifest.json --baseline R36_ARTIFACT_DIRECTORY
```

mailbox 검사는 실제 제품 패치를 임시 전체 소스에 fuzz 0으로 적용/역적용하고 round trip을 확인한 뒤 실제 함수를 추출한다. baseline과 이미 패치된 prepared 입력 모두 허용하며 필수 `--source`를 지정한다. `--patch`로 정확한 패치를 따로 지정할 수 있다. Clang과 ASan/UBSan을 사용하며 의존성을 설치하거나 공유기에 접속하지 않는다.

모형은 A 요청 timeout → B 시도 → A 늦은 응답의 한 가지 순서를 지정한다. 원본은 B가 A 응답을 성공으로 받아들이는 차이를 보여야 하고, 후보는 B에서 `-EBUSY`와 전체 요청·reply 상태 보존을 확인한 뒤 A 완료 후 B를 정상 진행시켜야 한다. 정상/오류/미완료 bit 조합, 초기 상태, trailing GET·SET·no-reply, read 오류 및 기존 입력 검사를 포함한다. 예상 실패는 정확한 실패 사유를 대조하며 sanitizer 오류를 통과로 세지 않는다. 실제 firmware 실행·DMA·IRQ 동시성·wall-clock timeout을 검증하는 시험은 아니다.

이미지 검증의 r36 baseline에는 `build-manifest.json`과 `verified-image/{rootfs/,metadata.json,dtb,kernel.gz}`가 필요하다. `airoha_npu.ko`만 달라져야 하며 kernel, 나머지 73개 모듈, 모든 NPU/Wi-Fi firmware와 wpad/LuCI 파일은 같아야 한다. package 이름 목록과 exact kernel ABI, 실제 새 ipkg module payload, FIT hash·metadata, Tailscale 및 bridge 설정 보존을 검사한다.

기존 TX/RX publication·링크 전환·forward path·WCID 수명·MLO PS·watchdog·TTL·conntrack·PPE·FDB·설치된 updater UI 검사도 현재 소스와 이미지에서 실행한다. 빌드 경고는 제거됐다고 가정하지 않고 `BUILD_WARNINGS.json`으로 집계한다. 이 결과를 설치·부팅·유선·Air 실물 시험 성공으로 해석하지 않는다.
