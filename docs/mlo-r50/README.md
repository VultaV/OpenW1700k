# r50 — 송신 출력 점검과 MLD 링크별 출력 표시 수정

r49 위에서 mt76 패치 하나(0039)와 wifi7 안내문만 바뀐 버전입니다. 2026-10-10 실제 장치에 설치해 확인했습니다.
커널 ABI \`6.18.55-w1700k-mlo-r32\`, 모듈 74개, 무선·NPU 펌웨어, 패키지 목록은 r49와 같고, 바뀐 패키지는
\`kmod-mt76*\`(r35)와 \`luci-app-wifi7\`(r20261010)뿐입니다. MLO 간헐 멈춤의 해결 여부는 바뀌지 않았습니다.

## 송신 출력 점검 (2026-10-10, r49 장치)

사용자가 출력을 최대로 올려 달라고 해서 대역별 상한과 실제 적용값을 확인했습니다.

| 대역 | 채널 | KR 규제 상한 (\`iw reg get\`) | 실제 적용 | 비고 |
|---|---|---:|---:|---|
| 2.4 GHz | 1 / 20 MHz | 23 dBm | 23 dBm | 상한 |
| 5 GHz | 36 / 160 MHz | 23 dBm (5150–5230) | 23 dBm | 단일 링크 AP(phy0.1-ap0)로 바꿔 직접 읽음. MLD에서는 \`iw\`가 18로 잘못 표시(아래) |
| 6 GHz | 37 / 160 MHz | 18 dBm (5925–6425), 6425 이상 15 dBm | 18 dBm | 상한 |

- UCI \`txpower\`는 설정하지 않은 상태(auto)이며, 이 상태가 각 대역의 규제·EEPROM 상한입니다. \`iw dev … set txpower fixed\`로
  더 높은 값을 줘도 규제값에서 잘립니다. 세 대역 모두 이미 상한이라 올릴 값이 없고, 더 올리려면 국가 코드를
  바꿔야 하므로 하지 않았습니다.
- **표시 결함**: \`mt7996_get_txpower()\`가 \`link_id\`를 무시하고 MLD 기본 링크(이 장치에서는 6 GHz) phy의 값을
  모든 링크에 돌려줘, \`iw dev ap-mld0 info\`와 WiFi 7 Overview가 5 GHz 링크도 18 dBm으로 보였습니다. mac80211의
  링크 설정값(debugfs \`link-1/txpower\`)은 23이었고, 5 GHz phy에는 자기 링크의 23 dBm이 적용되어 있었습니다
  (\`fixed 1500\` → 두 링크 모두 15, \`auto\` → 18/18로 돌아오는 것으로 기본 링크 phy만 읽는 것을 확인).

## 바뀐 점

- mt76 0039: \`mt7996_get_txpower()\`가 \`link_id\`로 링크를 찾아 그 링크의 phy 출력을 돌려주고, 링크에 phy가 없을
  때만 기본 링크로 되돌아갑니다. \`kmod-mt76\` r35.
- luci-app-wifi7 r20261010: "Collect logs" 안내문을 실제 동작(텍스트 파일 다운로드)에 맞췄습니다.

## 실기기 확인 (2026-10-10)

| 항목 | 결과 |
|---|---|
| 설치 | r49에서 설정 유지 sysupgrade, \`sysupgrade -T\` "Signature check OK". 유선 HTTP 2초 감시: 첫 실패 16:26:30, 복구 16:28:08 KST(약 98초) |
| 설정 보존 | wireless·bridge-flow-offload md5 일치, Tailscale 실행 중 |
| 부팅 | 커널 \`6.18.55-w1700k-mlo-r32\`, 모듈 74개, NPU 예산 가드 적용, 커널 경고 0 |
| 출력 표시 | \`iw dev ap-mld0 info\`: 5 GHz 링크 23.00 dBm, 6 GHz 링크 18.00 dBm; 2.4 GHz 23.00 dBm. \`fixed 2300\`→\`auto\` 뒤에도 23/18 |
| LuCI(Safari) | WiFi 7 Overview: Link 1 Tx 23.00 dBm, Link 2 Tx 18.00 dBm, 2.4 GHz 23.00 dBm |
| Mac MLO 5+6 (iperf3 4흐름 30초, AWDL 켜짐) | 하향 1,964 Mbps(최저 1,791), 상향 1,810 Mbps |

## 빌드

[r49 절차](../mlo-r49/README.md)와 같고 \`r50.config\`와 \`build-manifest.json\`을 씁니다. mt76만 다시 빌드한 뒤
이미지를 만들었습니다(빌드 경고 0). 빌드한 코드 커밋은 \`1e7d147b87\`이며 이 문서는 그 위에 따로 커밋했습니다.

## 알려진 제약

- WiFi 7 Diagnostics의 "Per-link current TX power"는 mac80211 debugfs 설정값을 읽습니다(5 GHz 23, 6 GHz 18). Overview와
  \`iw\`는 드라이버 적용값입니다. 지금은 두 값이 같습니다.
- \`bridge-flow-offload\`는 설정의 두 포트(\`lan2\`, \`ap-mld0\`)에만 적용됩니다(r49 기록 참조).
