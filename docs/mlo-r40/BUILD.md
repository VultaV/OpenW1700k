# r40 빌드·검증

[고정 toolchain/feed/overlay 절차](../mlo-r34/BUILD.md)에 r40 source tag, `r40.config`, `build-manifest.json`을 적용한다. mt76 package는 r31, Ethernet은 r2, NPU는 r3, kernel release는 `6.18.44-w1700k-mlo-r32`를 유지한다. 개인 설정·백업·Tailscale 상태는 이미지에 넣지 않는다.

`BUILD_RESULT.json`의 9개 make 단계를 매번 실행한다. 완료 후 실제 prepared source에서 기존 12개 검사와 RED 검사 한 개를 실행한다.

```sh
python3 tests/test_mt7996_npu_red.py --source-dir "$MT76" \
  --patch package/kernel/mt76/patches/0036-mt7996-initialize-red-for-npu-offload.patch
python3 docs/mlo-r40/verify-image.py BUILD IMAGE NEW_OUTPUT \
  docs/mlo-r40/build-manifest.json --baseline R39_ARTIFACT_DIRECTORY
```

RED 검사는 실제 helper, WA wrapper, 전체 firmware init 함수를 추출한다. 후보는 50 PASS, r39 원본에 `--expect-baseline`을 주면 32 PASS와 `EXPECTED_MISSING_CONTRACT` 1건이다. 이는 r39에서 세 명령 대신 legacy WA disable 하나만 보내는 정확한 차이이며, 원래 무선 장애의 원인 증명은 아니다. 입력 patch 적용·역적용은 fuzz와 offset 없이 전체 파일을 복원해야 한다. 후보와 실제 prepared `mcu.c/h`의 byte/hash 일치를 별도 기록한다.

명령 payload의 endian·길이·reserved bytes, 순서와 오류 전파를 ASan/UBSan으로 검사한다. MCU transport와 선행 초기화는 stub이다. WA 적용 readback, firmware token 소유권, 실제 DMA·동시성·무선 성능은 검사 범위 밖이다.

이미지 baseline은 r39 manifest와 `verified-image/{rootfs/,metadata.json,dtb,kernel.gz}`다. `mt7996e.ko`만 변경되고 kernel·나머지 73개 모듈·NPU/Wi-Fi firmware·wpad/LuCI가 동일해야 한다. FIT hash, 모든 package 이름/ABI, 새 ipkg payload, Tailscale·bridge 보존과 updater UI도 검사한다. 빌드 경고는 성공 여부와 별도로 집계하며, 설치·부팅 결과는 후속 문서에 기록한다.
