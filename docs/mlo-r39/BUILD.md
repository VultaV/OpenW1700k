# r39 빌드·검증 재현

[고정 toolchain/feed/overlay 절차](../mlo-r34/BUILD.md)에 r39 source tag, `r39.config`, `build-manifest.json`을 적용한다. mt76 package는 r30, Ethernet은 `6.18.44-r2`, NPU는 `6.18.44-r3`, kernel release는 `6.18.44-w1700k-mlo-r32`다. 개인 설정·백업·Tailscale 상태를 이미지에 넣지 않는다.

`BUILD_RESULT.json`의 9개 make 명령을 모두 실행한다. 저장된 성공 기록으로 make의 의존성 검사를 건너뛰지 않는다. 전체 빌드가 끝난 뒤 실제 prepared source와 완성된 이미지를 검사한다.

```sh
python3 tests/test_mt7996_npu_aggregation.py \
  --source-dir "$MT76" --mac80211-dir "$MAC80211"
python3 docs/mlo-r39/verify-image.py BUILD IMAGE NEW_OUTPUT \
  docs/mlo-r39/build-manifest.json --baseline R38_ARTIFACT_DIRECTORY
```

새 회귀 검사는 같은 디렉터리의 기존 `test_mt76_ps_wake.py` extractor를 재사용한다. 수정 전 r38 mt76 source에서 `--expect-missing-npu-refresh`를 주면 16 PASS·2 EXPECTED_FAIL이어야 한다. 기대 실패는 수용한 NPU PPDU·MPDU 보고가 `last_tx`를 갱신하지 않아 실제 추출 timer가 세션을 종료하는 경우에 한정한다. 비정상 종료나 다른 실패를 기대 실패로 인정하지 않는다.

원본에 `--patch package/kernel/mt76/patches/0035-mt7996-refresh-npu-tx-aggregation-timer.patch`를 주면 임시 복사본에 fuzz 0으로 적용해 18 PASS·0 FAIL을 검사한다. 최종 prepared source에서도 패치 옵션 없이 같은 검사를 실행한다. 원본 전체 `mac.c`에 적용한 패치와 최종 prepared 파일의 byte/hash 일치는 `prepared-source-provenance.json`에 남긴다. 원본은 로컬 build artifact에만 보존하며 새 검사에 필요한 원본 revision은 r38 태그다.

fixture는 실제 dispatcher·refresh·timeout 콜백과 협상 대입을 사용하지만, 동기 timer와 HZ1000 환경이다. firmware TXS 생성·동시성·Air의 timeout·무선 안정성은 검증하지 않는다. 입력·patch·검사·extractor 해시는 `ba-regression-tests.json`의 출력에 포함한다.

이미지 baseline에는 r38 manifest와 `verified-image/{rootfs/,metadata.json,dtb,kernel.gz}`가 필요하다. `mt7996e.ko`만 변경돼야 하며 나머지 73개 모듈·kernel·DTB·NPU/Wi-Fi firmware·wpad/LuCI는 같아야 한다. package 이름 목록·exact kernel ABI·새 ipkg payload·FIT hash·metadata·Tailscale/bridge 보존 검사도 유지한다.

기존 mailbox·TX/RX publication·링크 전환·forward path·WCID 수명·MLO PS·watchdog·TTL·conntrack·PPE·FDB 검사와 새 BA 검사를 포함한 12개 소스 검사 프로그램을 최종 prepared source에서 실행한다. 이미지의 updater UI 검사와 빌드 경고 집계는 별도로 기록한다. 설치·부팅·추가 무선 시험을 대신하는 결과가 아니다.
