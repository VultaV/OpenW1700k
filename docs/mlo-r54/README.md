# r54 — 무선 사용자 영역·mac80211 upstream 추적과 오프로드 재적용 수정

r53 위에서 hostapd, wifi-scripts, netifd, ubus, ucode, mac80211(backports 7.2 패치), nftables·libnftnl을
OpenWrt upstream main(2026-10-16)으로 맞추고, 커널 수정 두 개와 브리지 오프로드 수정 하나를 더한 버전입니다.
mt76 드라이버, 무선·NPU 펌웨어, 커널 버전(6.18.55)은 r53과 같습니다. 2026-10-17 실제 장치에 설치해 확인했습니다.
MLO 간헐 멈춤의 해결 여부는 바뀌지 않았습니다.

## 배경

이 트리의 바탕(r36182)과 upstream main 사이에는 커밋 1,214개가 있고, 그중 무선·네트워크·generic 커널 262개를
분류했습니다(이 장치에 해당하는 버그 수정 104개, 기능 31개, 이미 있음 17개, 무관 110개). 해당 패키지에서 포크가
바꾼 부분이 작아서 패키지 단위로 upstream을 따르고 포크 변경만 다시 얹었습니다.

## 바뀐 점

- hostapd: AP MLD 수정 181~198(SA Query 시간 초과 뒤 재연결, 링크 추가 실패 정리, 링크 제거 알림, 링크별
  disassociation, 첫 링크 BSSID 유지, Non-Inheritance 요소 등), ubus 메모리 오류 수정, hostapd.uc의 MLD 유지·재설정.
  포크 패치 `999-preserve-link-id-for-unknown-station`(upstream 185와 동일)과 `9999-reset-expired-mld-before-link-setup`
  (upstream 181로 대체)을 뺐고, `9999-deliver-dfs-state-to-unconfigured-links`는 유지합니다.
- mac80211: 다른 링크가 비컨을 보내는 동안 MLD 인터페이스 상태·carrier 유지, 관리 프레임의 링크 선택, 802.3 encap
  대역, MLO 단말 통계 등. 포크 패치 두 개(fdb notify, TXQ rearm)는 새 코드에 맞췄습니다.
- wifi-scripts·netifd·ubus·ucode: MLD 하위 설정 변경 때 전체 재시작을 피함, 6 GHz/EHT RSN 기본값, rtnl ACK 처리 등.
- 커널: flowtable이 출력 경로를 찾지 못한 흐름을 ifindex 0으로 오프로드해 패킷을 버리던 문제(upstream `aa9479b02e`),
  QE 비트가 없는 SPI-NAND에서 QE를 건드리던 문제(upstream `d42c59d039`, r53의 W25N04LV에 해당).
- bridge-flow-offload r4: wifi reload로 ap-mld0이 다시 만들어지면 브리지에 붙기 전의 hotplug 이벤트에서 오프로드를
  끄고 다시 켜지 않던 문제를 고쳤습니다. 포트가 forwarding이 되면(최대 30초) 다시 적용합니다. r53에서 실제로
  재현했고, 호스트 시험에 회귀 시험을 추가했습니다.

## 실기기 확인 (2026-10-17)

| 항목 | 결과 |
|---|---|
| 설치 | r53에서 설정 유지, `sysupgrade -T` "Signature check OK", 약 90초 만에 접속 |
| 부팅 | 커널 경고 0, NPU 버전 0.1111, Tailscale 연결 |
| 무선 | MLO 5 GHz(ch36)·6 GHz(ch37) 160 MHz, 2.4 GHz. 송신 출력 23/18/23 dBm |
| Mac 재연결 3회 | 매번 MLO 두 링크(valid_links 0x0006, primary 6 GHz) |
| Mac 무선(iperf3 4흐름 30초) | 하향 1,729·2,003·1,972 Mbps, 상향 1,796·1,816 Mbps, 500 Mbps 미만 구간 0 |
| 2.4 GHz 설정 변경·복구 | MLO 단말 연결 유지(연결 시간 203→243→283초), 오프로드 유지 |
| MLO SSID 설정 변경·복구 | 단말이 다시 접속해 두 링크 복구, 오프로드 유지, 커널 경고 0 |
| 오프로드 흐름 | 140~187개 |

## 알려진 제약

r51과 같습니다([r51 기록](../mlo-r51/README.md)). hostapd 로그의 "Can't set DFS state for freq 5180–5240 MHz"
경고는 r53에도 있던 것입니다.
