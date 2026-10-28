# r58 — upstream 보안·flowtable·사용자 영역 묶음

r57 위에서 OpenWrt upstream main(2026-10-28)의 커밋 16개를 가져오고, 브리지 오프로드 패치를 다시 맞춘 버전입니다.
mt76, hostapd, mac80211, 무선·NPU 펌웨어, 커널 버전(6.18.55)은 r57과 같습니다. 2026-10-28 실제 장치에 설치해
확인했습니다. MLO 간헐 멈춤의 해결 여부는 바뀌지 않았습니다.

## 바뀐 점

- 보안: dnsmasq CVE 수정 7건(`6db25ee835`, 앞선 VRF 지원 `71588f0d76`·느린 로딩 수정 `0dfc92701b` 포함), musl
  regcomp 정수 오버플로(`f1d43d5297`).
- flowtable·브리지: `706-03`(포워드 경로를 찾지 못하면 오프로드하지 않음, `699` 대체, `2d7e2a4ae6`), `708` v9
  (`09fe0f8140`), `706-04` VLAN ID(`be75fbfa9b`), DSA 호스트 FDB 포트별 관리 `642`/`643`(`c7924dcd74`).
- 무선·사용자 영역: wifi-scripts sae_pwe(6 GHz 링크가 있는 AP MLD, `c9ea07732f`, `035a94fdb5`), ucode 2026-10-23
  (`fff992f940`), firewall4 2026-10-26(`e2e50c9dc4`), netifd 2026-10-28과 패킷 스티어링(`e1dd989404`, `cd6b08f2b5`,
  `8a97b52c3a`, `0747c5b488`).
- 포크 패치:
  - `675-02`: 새 `706-03` 구조 위에 다시 맞췄습니다. 브리지 흐름은 이더넷 헤더에서 주소를 얻고 flowtable 장치 검사를
    건너뛰며, VLAN 없는 untag와 MTK WDMA 경로를 허용합니다. 포워드 경로를 찾지 못하면 브리지 흐름도 기본 경로로
    남습니다(r57까지는 알 수 없는 경로 항목을 넘겼음).
  - `9999-z7`(없는 호스트 FDB 삭제를 성공 처리)을 뺐습니다. `643`이 포트마다 보유한 주소를 기록해 같은 경우를 무시합니다.
- 코드 리뷰(2026-10-28)를 거쳐 위 두 가지를 반영했습니다. 리뷰에서 나온 VLAN 브리지 흐름의 `708` 상호작용은 이 장치가
  VLAN 브리지를 오프로드하지 않아 보류했습니다.

## 실기기 확인 (2026-10-28)

| 항목 | 결과 |
|---|---|
| 설치 | r57에서 설정 유지, `sysupgrade -T` "Signature check OK", 약 100초 만에 접속 |
| 부팅 | 커널 경고 0, MLO 5 GHz·6 GHz 160 MHz, DNS·인터넷 정상 |
| fw4 flowtable | `br-lan` 대신 브리지 하위 포트(ap-mld0, lan2, lan3, lan4, phy0.0-ap0)와 tailscale0, wan. 브리지 오프로드 테이블(ap-mld0, lan2)과 함께 동작 |
| 오프로드 흐름 | 부팅 직후 241개, WAN 쪽 오프로드 흐름 704개 |
| RPS | eth0·lan2·wan이 CPU0에서 CPU1~3으로 바뀜(인터럽트 CPU를 피함). Wi-Fi RPS, mt76 송신 작업, Wi-Fi NAPI 배치는 r57과 같음 |
| Mac 재연결 3회 | 매번 MLO 두 링크(valid_links 0x0006, primary 6 GHz) |
| Mac 무선(iperf3 4흐름 30초) | 하향 1,936·1,956·1,958 Mbps, 상향 1,791·1,818 Mbps, 500 Mbps 미만 구간 0 |
| 인터넷(networkQuality, WAN 1 GbE) | 하향 898 Mbps, 상향 773 Mbps |

- 설치 직후 첫 측정에서는 재연결 뒤 Mac이 iperf 서버에 "No route to host"로 접속하지 못했습니다. 이후 다시 잰 측정과
  재연결 5회(매번 1초 안에 접속)에서는 재현되지 않았습니다.

## 알려진 제약

r57과 같습니다([r57 기록](../mlo-r57/README.md)).
