# r55 — ucode 2026-10-18과 맞물린 사용자 영역 갱신

r54 위에서 ucode를 OpenWrt upstream main(2026-10-18, upstream `a4e922953c`)으로 올린 버전입니다. 커널, mt76,
hostapd, mac80211, 무선·NPU 펌웨어는 r54와 같습니다. 2026-10-19 실제 장치에 설치해 확인했습니다. MLO 간헐 멈춤의
해결 여부는 바뀌지 않았습니다.

## 바뀐 점

- ucode 2026-10-18: json·zlib의 read 메서드 use-after-free, gc sweep, filter/map/poll 값 고정, ubus 지연 응답 누수 수정.
  r54가 의존하던 rtnl ACK 처리는 이제 ucode 본체에 들어 있습니다. 라이브러리 soname이 `libucode20230711`에서
  `libucode20261009`로 바뀌었습니다.
- 새 ucode 헤더에 맞춘 갱신:
  - uhttpd를 upstream(2026-08-24)으로 맞췄습니다. URL 접두어 핸들러의 Basic Auth realm 강제(GHSA-5cgm-8h9x-v28c)가
    함께 들어옵니다.
  - uhttpd와 rpcd의 ucode 플러그인에 새 `STATUS_BREAK` 상태 처리를 넣었습니다(디버거 중단 요청 전용, 실행 오류로
    처리). upstream main은 이 시점에 이 두 패키지가 `-Werror=switch`로 빌드되지 않습니다.
  - udebug를 upstream(2026-09-25)으로 맞췄습니다(새 헤더가 fcntl.h를 포함하지 않음).
  - 상태 enum 값이 바뀌었으므로 ucode를 쓰는 netifd, rpcd, wpad, uhttpd, uclient, lucihttp, ucode-mod-html,
    luci-base를 다시 빌드했습니다. 이미지의 libucode 사용 바이너리는 모두 새 soname에 링크됩니다.
- 원격 snapshot 피드의 ucode 관련 패키지는 soname이 맞지 않을 수 있습니다. 이미지 안의 패키지끼리는 문제가 없습니다.
- 이미지에 들어간 `build-manifest.json`의 `built_source_commit`은 `e6073c24a3`입니다. 이미지는 그 뒤의 udebug 커밋
  `12aac184d2`까지 포함해 빌드했습니다.

## 실기기 확인 (2026-10-19)

| 항목 | 결과 |
|---|---|
| 설치 | r54에서 설정 유지, `sysupgrade -T` "Signature check OK", 약 95초 만에 접속 |
| 부팅 | 커널 경고 0, NPU 버전 0.1111, Tailscale 연결, netifd·rpcd·uhttpd·hostapd 동작 |
| LuCI | 로그인 화면(`luci_password`), `/ubus` 세션 RPC 응답, rpcd ucode 플러그인(luci, luci-rpc) 응답 |
| 무선 | MLO 5 GHz(ch36)·6 GHz(ch37) 160 MHz, 2.4 GHz. 송신 출력 23/18/23 dBm |
| Mac 재연결 3회 | 매번 MLO 두 링크(valid_links 0x0006, primary 6 GHz) |
| Mac 무선(iperf3 4흐름 30초) | 하향 1,980·1,991·1,989 Mbps, 상향 1,643·1,735·1,831·1,812 Mbps, 500 Mbps 미만 구간 0 |
| 2.4 GHz 설정 변경·복구 | MLO 단말 연결 유지(264→304→344초), 두 링크 유지 |
| MLO SSID 설정 변경·복구 | 단말이 두 링크로 다시 접속, 오프로드 유지 |
| 로그 | 커널 경고 0, hostapd·netifd·ucode 예외·런타임 오류 0. 오프로드 흐름 176개 |

## 알려진 제약

r54와 같습니다([r54 기록](../mlo-r54/README.md)).
