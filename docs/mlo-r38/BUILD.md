# r38 빌드·검증 재현

[고정 toolchain/feed/overlay 절차](../mlo-r34/BUILD.md)를 사용하되 r38 source tag, `r38.config`, `build-manifest.json`을 적용한다. Ethernet package는 `6.18.44-r2`, NPU package는 `6.18.44-r3`, mt76은 `r29`, kernel release는 `6.18.44-w1700k-mlo-r32`다. 개인 설정·백업·Tailscale 상태를 이미지에 넣지 않는다.

`BUILD_RESULT.json`에 기록된 9개 make 명령을 모두 실행한다. 이전 성공 기록을 이유로 make의 의존성 검사를 건너뛰지 않는다. 완료 후 실제 prepared source와 이미지를 검사한다.

```sh
python3 tests/test_airoha_ppe_ownership.py "$KERNEL/drivers/net/ethernet/airoha/airoha_ppe.c"
python3 docs/mlo-r38/verify-image.py BUILD IMAGE NEW_OUTPUT \
  docs/mlo-r38/build-manifest.json --baseline R37_ARTIFACT_DIRECTORY
```

PPE 검사는 실제 함수와 header를 추출해 기존 ownership 11건과 새 flush 5건을 ASan/UBSan으로 실행한다. 수정 전 r37 전체 C 소스와 같은 header를 명시하고 `--flush-baseline`을 붙이면 세 오류 주입에서 반환값이 정확히 잘못된 0인지 확인한다. 이때 13 PASS·3 EXPECTED_FAIL이어야 하며 비정상 종료·sanitizer 오류를 기대 실패로 인정하지 않는다. 후보는 16 PASS·0 EXPECTED_FAIL이다. 전체 파일에 정식 패치를 fuzz 0으로 적용한 결과와 최종 prepared 파일의 byte 일치는 `prepared-source-provenance.json`에 남긴다.

실제 SRAM ACK/MMIO·IRQ 동시성·probe cleanup·부팅은 이 fixture가 검증하지 않는다. 현재 source의 전체 caller와 오류 정리 순서는 별도 [검토](REVIEW.md)에 기록한다.

이미지 baseline에는 검증된 r37 manifest와 `verified-image/{rootfs/,metadata.json,dtb,kernel.gz}`가 필요하다. `airoha-eth.ko` 하나만 변경돼야 하며 나머지 73개 모듈·kernel·DTB·NPU/Wi-Fi firmware·wpad/LuCI는 같아야 한다. package 이름 목록·exact kernel ABI·새 ipkg payload·FIT hash·metadata·Tailscale/bridge 보존 검사도 유지한다.

기존 mailbox·TX/RX publication·링크 전환·forward path·WCID 수명·MLO PS·watchdog·TTL·conntrack·FDB·updater UI 검사를 최종 소스와 이미지에서 실행한다. 모든 단계 로그의 경고는 `BUILD_WARNINGS.json`에 별도로 기록한다. 결과를 설치·부팅·무선 안정성 성공으로 해석하지 않는다.
