# r57 — flow offload 상태의 로밍 수정

r56 위에서 OpenWrt upstream의 flow offload 로밍 수정 두 건을 가져온 버전입니다. mt76, hostapd, ucode, 무선·NPU
펌웨어, 커널 버전(6.18.55)은 r56과 같습니다. 2026-10-25 실제 장치에 설치해 확인했습니다. MLO 간헐 멈춤의 해결
여부는 바뀌지 않았습니다.

## 바뀐 점

- `279704475c` kernel: import fixes for roaming under flow-offloading
  - `706-01` (v7.3) `dev_fill_forward_path()`가 `net_device_path_ctx`를 받도록 바뀜.
  - `706-02` (v7.3) ieee80211 포워드 경로 복구.
  - `708` (pending) 출력 장치가 바뀐 direct-xmit 흐름을 정리. DSA 포트 사이나 MAC 사이를 옮긴 단말의 오프로드 흐름이
    끊기던 문제.
- `d014acb494` mac80211: flowtable restore ieee80211 forward path(subsys 007).
- 포크 브리지 오프로드 패치 재적용:
  - `675-01`: 이제 602 백포트가 하는 `__dev_fill_forward_path()` 도입을 뺐습니다(OpenWRT-fanboy의 재적용과 같음).
  - `675-02`: 호출부의 ctx를 `nft_dev_fill_forward_path()`에 넘기고 거기서 `.ieee80211 = true`를 설정합니다. 브리지
    흐름에서 모든 경로 항목의 장치를 indev로 잡는 기존 동작은 유지했습니다.
  - `699`(out ifindex 대체값)는 기존 위치를 유지했습니다.
- 넣지 않은 것: `e642288a36`(airoha Wi-Fi 로밍 PPE 정지 수정)은 OpenWrt main이 아닌 개인 브랜치의 미병합 패치라
  보류했습니다.

## 실기기 확인 (2026-10-25)

| 항목 | 결과 |
|---|---|
| 설치 | r56에서 설정 유지, `sysupgrade -T` "Signature check OK", 약 115초 만에 접속 |
| 부팅 | 커널 경고 0, MLO 5 GHz·6 GHz 160 MHz, Tailscale 연결 |
| flowtable | fw4 `ft`(br-lan, tailscale0, wan)와 브리지 `ft`(ap-mld0, lan2, offload) 생성. 부팅 직후 오프로드 흐름 204개 |
| Mac 재연결 3회 | 매번 MLO 두 링크(valid_links 0x0006, primary 6 GHz) |
| Mac 무선(iperf3 4흐름 30초, 브리지 오프로드) | 하향 1,962·1,971·1,960 Mbps, 상향 1,802·1,802 Mbps, 500 Mbps 미만 구간 0 |
| 인터넷(networkQuality, WAN 1 GbE) | 하향 887 Mbps, 상향 783 Mbps |
| 로그 | 커널 경고 0 |

- 단일 AP라 실제 AP 간 로밍과 DSA 포트 사이 이동은 재현하지 못했습니다. Tailscale 경유 포워딩 경로도 이번에는 측정하지
  못했습니다(LAN 안의 Mac은 직접 경로를 씀).

## 알려진 제약

r56과 같습니다([r56 기록](../mlo-r56/README.md)).
