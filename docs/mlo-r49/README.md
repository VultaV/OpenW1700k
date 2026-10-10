# r49 — 사용자 영역·드라이버 오류 처리 보강

r48의 커널 6.18.55 위에서, 오류를 삼키던 경로를 고치고 LuCI 보드 앱의 root 상태 파일 쓰기를 안전하게
바꾼 버전입니다. 2026-10-10 실제 장치에 설치해 유선·무선·LuCI를 확인했습니다. 커널 ABI는
\`6.18.55-w1700k-mlo-r32\` 그대로이고 모듈 74개·펌웨어 11개·패키지 목록은 r48과 같습니다.
MLO 간헐 멈춤의 해결 여부는 바뀌지 않았습니다.

## 바뀐 점

- airoha 999-dsa-01: MT7531 netlink PHY 읽기·쓰기의 MDIO 오류를 성공처럼 돌려주던 것을 netlink 오류로
  돌려줍니다. 992-21: 121이 추가한 NPU BA 예약 메모리 명령만 재시도 도우미를 거치지 않아 일시 오류가
  WLAN NPU 초기화를 중단시키던 것을 같은 도우미로 보냅니다.
- mt76 0011: SKU 갱신 MCU 호출이 실패하면 캐시한 txpower를 되돌려 같은 요청이 다시 시도되게 합니다.
  0006: NPU RX 디스크립터가 큐에 있는 것보다 많은 프레임을 알리면 멈춤을 조용히 넘기지 않고 rate-limit
  로그를 남깁니다. \`kmod-mt76\` r34.
- w1700k-wifi-watchdog 2: 상태·잠금 디렉터리를 sticky \`/tmp\`에서 \`/var/run\`으로 옮겼습니다.
- 보드 LuCI 앱: FlowSense rpcd 백엔드·jitter 데몬·airtime 상태는 mktemp+rename으로 씁니다. NPU PLL
  설정은 devmem 쓰기 실패를 "register write failed"와 readback 값으로 보고합니다. wifi7은 OWE·OWE-transition
  프로필을 키 없이 저장할 수 있고, "Collect logs"가 ACL에 있는 dmesg·logread를 직접 호출합니다(이전에는
  /bin/sh를 불러 빈 결과를 Done으로 표시). 팬 설정의 프리셋 미리보기가 갱신되고, netspeedtest 결과 링크는
  완전한 http(s) URL만 링크가 됩니다.

## 빌드

[r48 절차](../mlo-r48/README.md)와 같고 \`r49.config\`와 \`build-manifest.json\`을 씁니다. \`.config\`는
r48과 버전 문자열만 다릅니다. 커널 패치가 바뀌어 \`make target/linux/clean\` 뒤 전체 빌드(약 19분, Darwin arm64),
mt76 PKG_RELEASE 반영 뒤 mt76·이미지 재빌드. 빌드 경고 0, \`distfeeds.list\`는 r46 형식(사용자 영역 피드 4개).
빌드한 코드 커밋은 \`b4695e771e\`이며 이 문서는 그 위에 따로 커밋했습니다.

## 실기기 확인 (2026-10-10)

| 항목 | 결과 |
|---|---|
| 설치 | r48에서 설정 유지 sysupgrade, \`sysupgrade -T\` "Signature check OK". 유선(lan4) HTTP 2초 감시: 첫 실패 15:06:57, 복구 15:08:37 KST(약 100초) |
| 설정 보존 | wireless·network·firewall·dhcp·bridge-flow-offload md5 일치, Tailscale 상태 보존·실행 중 |
| 부팅 | 커널 \`6.18.55-w1700k-mlo-r32\`, 모듈 74개, apk 패키지 210개, \`w1700k-fit-check\` 존재, 커널 경고 0 |
| NPU | "NPU TX budget guard applied", NPU fw 0.1111, NPU RED WM ACK |
| 무선 | 세 라디오 up, MLO 5 GHz(ch36)+6 GHz(ch37) 각 160 MHz, 브리지 오프로드 lan2↔ap-mld0 |
| 워치독 | \`/var/run/w1700k-wifi-watchdog\`에 상태, \`/tmp\`에는 없음 |
| LuCI(Safari) | Overview·Wireless·MLO·WiFi 7(Overview/Diagnostics)·SoC Status·FlowSense·Fan·SpeedTest·Channel Analysis·Attended Sysupgrade 렌더링, 오류 문자열 없음 |
| WiFi 7 Collect logs | dmesg 36줄 + logread 200줄이 든 텍스트 파일 다운로드(r48은 빈 결과) |
| 팬 프리셋 미리보기 | 프리셋을 바꾸면 곡선이 바로 바뀜(Reset으로 되돌림, 저장 안 함) |
| FlowSense | 상태 파일 \`/tmp/npu-*.prev\`·\`npu-jitter.json\` 0600, jitter 데몬 실행, \`fs.protected_symlinks=1\` |

## Mac 처리량 (iperf3 4흐름, 2.5GbE Linux 서버)

Mac(M5 Pro, macOS 27, Wi-Fi 7) ↔ 2.5GbE lan2의 iperf3 서버. 무선은 30초, 유선은 20초. AWDL은 sudo를 쓸 수
없어 켜진 채였고, macOS 설정의 Wi-Fi 화면은 열지 않았습니다. 평균은 수신 측, 최저는 1초 구간입니다.

### 유선 (Mac 어댑터는 lan4 1GbE)

| 경로 | 하향 | 상향 |
|---|---:|---:|
| 스위치 lan4↔lan2 (서버) | 844 Mbps (최저 680) | 932 Mbps |
| 공유기 CPU 끝점 (iperf3 서버 192.168.1.1) | 864 Mbps | 930 Mbps |
| WAN networkQuality (유선) | 815 Mbps | 818 Mbps, 응답성 High |
| WAN networkQuality (Wi-Fi) | 870 Mbps | 724 Mbps, 응답성 High |

### 무선 구성별

| AP 구성 | Mac 연결 | 하향 (회차별 평균 / 최저) | 상향 |
|---|---|---|---|
| MLO 5+6 (출하 설정) | 링크 1+2, primary 6 GHz | 1,216(76)·1,993(1,859)·1,984(1,838) | 1,812·1,804 |
| 단일 5 GHz, 오프로드 없음 | ch36 160 MHz | 1,478(1,340)·1,398(1,282) | 789 |
| 단일 5 GHz, 오프로드 phy0.1-ap0 | ch36 160 MHz | 1,987(1,750)·1,977(1,749) | 1,797 |
| 단일 6 GHz, 오프로드 phy0.2-ap0 | ch37 160 MHz | 1,670(411)·1,965(1,864) | 1,775 |
| MLO 2.4+5+6, Mac이 2.4 GHz로 접속 | 링크 0+2, primary 2.4 GHz | 158(118)·158(100) | 108 |
| MLO 2.4+5+6, Wi-Fi 껐다 켜서 재접속 | 링크 0+1+2, primary 6 GHz | 637(0, 0 Mbps 6초)·1,977(1,906) | 1,529(61) |
| MLO 5+6 복원 후 | 링크 1+2, primary 6 GHz | 1,966(1,872)·1,959(1,818) | 1,810 |

관찰:

- \`bridge-flow-offload\`는 설정의 두 포트(\`lan2\`, \`ap-mld0\`)에만 적용됩니다. MLO를 끄면 Wi-Fi netdev가
  \`phy0.N-ap0\`이 되어 오프로드가 "unknown wireless port"로 내려가고 CPU 경로(하향 1.4–1.5 Gbps, 상향 0.8 Gbps)로
  돌아갑니다. 포트를 새 netdev로 바꾸면 단일 링크도 MLO와 같은 1.98 Gbps입니다. 포트 자동 추적은 이번에 넣지 않았습니다.
- 이 Mac은 한 번에 한 링크만 씁니다(다른 링크는 절전). 3링크 MLD에서 2.4 GHz로 접속하면 primary가
  2.4 GHz가 되어 158 Mbps에 머물고, 6 GHz로 다시 붙어도 첫 하향 회차에 0 Mbps 6초가 있었습니다. 5+6 MLO가
  가장 좋은 구성이라 출하 설정을 그대로 두었습니다. 3링크 AP 자체는 hostapd·드라이버에서 정상으로 올라왔습니다.
- 2링크 MLO와 단일 6 GHz 모두 새 접속 직후 첫 하향 회차가 느렸고(1,216·1,670 Mbps) 이후 회차는 1.96–1.99 Gbps였습니다.
  r41·r46에서 본 접속 초기 저하·AWDL 절전 전환과 같은 양상이며 원인은 확정하지 않았습니다.
- 시험 뒤 \`/etc/config/wireless\`와 \`bridge-flow-offload\`를 바이트 단위로 복원했습니다(md5 일치). 원시 JSON과
  설정 백업은 로컬에만 두었습니다(단말 식별자 포함).

## 알려진 제약

- WiFi 7 Diagnostics의 "Per-link current TX power"는 mac80211 debugfs(\`link-N/txpower\`, 설정값)를 읽어 5 GHz 링크에
  23 dBm을 보이고, \`iw\`는 18 dBm(실제 적용값)을 보입니다. 표시 기준이 다를 뿐 동작 차이는 아닙니다.
- "Collect logs" 안내문은 "새 탭에 열림"이지만 실제로는 텍스트 파일을 내려받습니다. 문구는 r49 이미지 뒤 소스에서 고쳤습니다.
- 이 드라이버의 MLO 구성에서는 5·6 GHz 채널 스캔을 할 수 없습니다.
