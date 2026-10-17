# r52 — upstream 0 dBm 송신 출력 수정과 mt7530 VLAN 백포트

r51 위에 OpenWrt upstream 커밋 두 개만 더한 버전입니다. mt76 드라이버, 무선·NPU 펌웨어, 커널 버전과 설정은
r51과 같습니다. 2026-10-16 실제 장치에 설치했고, 2026-10-17 무선 처리량·재연결·0 dBm 적용을 확인했습니다. MLO 간헐 멈춤의 해결 여부는 바뀌지 않았습니다.

## 바뀐 점

- `5ee6f1fdbe` wifi-scripts: UCI `txpower`를 0으로 두면 auto로 처리되던 문제를 고칩니다
  (`if (config.txpower)` → `if (config.txpower != null)`).
- `3a985c7398` kernel: Linux v7.1의 mt7530 VLAN 수정 두 개를 백포트합니다(`721-01` VLAN-aware 브리지를 없앤 뒤
  CPU 포트를 VLAN-unaware로 되돌림, `721-02` VLAN-aware 브리지의 PVID를 untag). 이 장치의 스위치 드라이버
  (`kmod-dsa-mt7530`, `kmod-dsa-mt7530-mmio`)에 해당합니다.
- 두 커밋은 w1700k/builds `ubi2-oc` 2026-10-14 빌드가 바탕으로 쓴 OpenWrt main에서 가져왔습니다. 그 빌드의
  CPU 오버클럭은 넣지 않았습니다.

## 빌드

- r51 트리에서 cherry-pick(`-x`) 두 개. 커널 패치는 모두 적용되었고 기존 `746`(mt7530 리셋 GPIO) 패치만
  13줄 오프셋이 생겼습니다(fuzz 없음).
- 패키지 manifest는 r51과 같습니다. 바뀐 파일은 `mac80211.sh`와 mt7530 모듈 두 개입니다.

## 실기기 확인 (2026-10-16, 원격)

| 항목 | 결과 |
|---|---|
| 설치 | r51에서 설정 유지, `sysupgrade -T` "Signature check OK", 약 95초 만에 접속 |
| 부팅 | 커널 `6.18.55-w1700k-mlo-r32`, 커널 경고 0, NPU 버전 0.1111 응답 |
| 무선 | MLO 5 GHz(ch36)·6 GHz(ch37) 160 MHz, 2.4 GHz. 송신 출력 23/18/23 dBm(r51과 같음) |
| 유선 | wan·lan2·lan3·br-lan up, 인터넷 연결 정상 |
| 0 dBm 수정 | 이미지의 `mac80211.sh`에 반영됨을 확인 |

## 실기기 시험 (2026-10-17)

| 항목 | 결과 |
|---|---|
| 0 dBm | 2.4 GHz `txpower=0` → netifd "fixed 000", `iw` 0.00 dBm. 설정을 지우면 23.00 dBm(auto)으로 돌아옴. r51까지는 0이 auto로 처리됨 |
| Mac 재연결 3회 | 매번 MLO 두 링크(valid_links 0x0006, primary 6 GHz, secondary 5 GHz) |
| 브리지·오프로드 | lan2·ap-mld0 브리지 정상, 오프로드 흐름 123개, 커널 경고 0 |
| Mac 무선(iperf3 4흐름 30초) | 하향 2,013·2,024·2,018 Mbps(최저 1,941), 상향 1,833·1,832 Mbps(최저 1,747), 500 Mbps 미만 구간 0 |

- 상향을 처음 쟀을 때 macOS 시스템 설정의 Wi-Fi 화면이 열려 있었고, 1,331 Mbps에 0 Mbps 구간이 4~6초 있었습니다.
  화면을 닫고 다시 재면 위 값이 나옵니다. r46에서 기록한 macOS 스캔·AWDL 영향과 같은 양상입니다.
- 측정 전 Mac에서 집 LAN 대역이 Tailscale subnet route(utun)로 나가고 있어, 측정하는 동안만 수신을 껐습니다.
- VLAN 구성은 쓰지 않으므로 mt7530 백포트는 기존 브리지 동작에 회귀가 없음만 확인했습니다.

## 알려진 제약

r51과 같습니다([r51 기록](../mlo-r51/README.md)).
