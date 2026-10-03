# 2c12af9 검토 — 2026-09-28

대상: https://github.com/OpenWRT-fanboy/OpenW1700k/commit/2c12af94ce461d6037e5c16ac257f70943b9a417
커밋 시각: 2026-09-27 09:06:03 UTC (18:06:03 KST). GitHub API의 전체 변경 파일 2개와 로컬 prepared Linux 6.18.44 소스를 읽기 비교했다. 장치 설정·소스 패치·펌웨어 설치는 하지 않았다.

## 변경과 적용 범위

- `670-net-loopback-raise-the-gso-size-limit.patch`: loopback setup에서 `gso_max_size`와 `gso_ipv4_max_size`를 `GSO_MAX_SIZE`로 설정한다. 기본 64 KiB 소프트웨어 분할 경계를 높이는 변경이며 대상은 lo다. mt76, Airoha, NPU 펌웨어 및 실제 LAN/Wi-Fi 장치의 GSO 한도는 이 패치로 변경하지 않는다.
- `671-net-tcp-raise-the-send-buffer-share-limit.patch`: `tcp_init()`의 `max_wshare` 한도를 4 MiB에서 32 MiB로 올린다. `limit = nr_free_buffer_pages() << (PAGE_SHIFT - 7)`은 그대로이며 이 결과가 `sysctl_tcp_wmem[2]` 초기값이 된다. 모든 장치에서 즉시 32 MiB를 배정한다는 뜻이 아니다. TCP 송신 endpoint의 기본값 변경이며 loopback 이외 로컬 TCP socket에도 적용 범위가 있다.

커밋의 약 15%·20% 개선은 작성자가 제시한 `127.0.0.1` loopback iperf 결과다. W1700K의 무선 처리량 향상이나 이번 장비 실측 결과가 아니다.

## 우리 시험과의 관계

기존 시험은 별도 Linux 서버와 Mac/Air 사이의 LAN→Wi-Fi 전달이다. 공유기는 시험 TCP의 endpoint가 아니며 lo를 통과하는 시험도 아니다. 따라서 공유기에 이 커밋을 넣는 것만으로 기존 시험의 TCP 송신 버퍼나 무선 PS/ACK 정체를 직접 수정하지 않는다. 공유기 자체 iperf 송신·loopback 성능에는 별도 검토 가치가 있다. 서버 OS나 Mac TCP 구현에 이 OpenWrt 패치가 자동 적용되는 것도 아니다.

로컬 `build-volume/source/build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-6.18.44/drivers/net/loopback.c:194`는 기존 `netif_set_tso_max_size()`만 사용하고, `net/ipv4/tcp.c:5303`은 여전히 `min(4UL*1024*1024, limit)`다. `publish-mlo-r29/target/linux/generic/hack-6.18`에도 해당 두 신규 파일은 없다. 즉 비교한 로컬 r43 빌드 소스에는 미반영이다. 실행 중 공유기 상태는 이번 검토에서 다시 조회하지 않았다.

결론: 커널 네트워크 스택 성능 패치이며 MLO/무선 드라이버/NPU 수정은 아니다. 현재 간헐 정체의 원인 해결 패치로 채택할 근거가 없으므로 이번 검토에서는 적용하지 않았다.
