# r61/r62 MLO 검증 계획 (2026-11-01)

MLO 끊김 문제는 아직 해결이 확인되지 않았습니다. 이 문서는 어디까지 측정할 수 있는지와 각 단계를 어떻게 판정할지 정합니다.

## 출발점: r60 측정 결과 (2026-11-01, Mac 1대, iperf3 4스트림 30초)

| MLD 조합 | Mac 링크 | 다운로드 Mbps | 업로드 Mbps |
|---|---|---|---|
| 2.4+5 | 0x0003, 데이터는 5 GHz | 1862 / 1952 / 1946 | 1802 / 1772 |
| 2.4+6 | 0x0005, primary 2.4 GHz | 163 / 142 / 132 | 84 / 91 |
| 5+6 | 0x0006 | 1966 / 1986 / 1915 | 1755 / 1817 |
| 2.4+5+6 | 0x0005(2.4+6), 1초 구간에 0 Mbps 발생 | 375 / 361 / 376 | 399 / 414 |

- 커널 경고는 0건이었습니다.
- `uci` 수정 후 `wifi reload`로 링크를 빼고 넣을 때마다 AP-STA-DISCONNECTED가 나고 다시 연결됐습니다. 0 Mbps 구간은 3~4초였습니다.
- r60에는 연결을 유지한 채 대역을 바꾸는 것을 측정할 도구가 없습니다.
  - hostapd는 ubus에 링크 제거 명령이 없습니다.
  - iw는 링크별·radio별 송신 출력을 설정하지 못합니다.
  - nl80211은 radio 번호가 붙은 SET_WIPHY 요청을 RTS만 처리하는 `nl80211_set_wiphy_radio()`로 보내고, 송신 출력 설정은 성공 응답만 남기고 버립니다(r61 A0에서 확인).

## r61: 링크 하나만 감쇠시키기 (이번 빌드)

변경 사항:

- iw `320-txpower-radio-index.patch`: `set txpower`가 `radio <idx>` 인자를 받습니다.
- mac80211 `9998-wifi-set-the-tx-power-of-one-radio-of-a-vif.patch`(PKG_RELEASE 13):
  - nl80211이 송신 출력 설정을 radio 번호와 함께 드라이버까지 넘깁니다.
  - mac80211 vif 경로는 해당 radio에 있는 링크에만 송신 출력을 적용합니다.
  - 처음 r61 이미지(mac80211 r12)에는 mac80211 쪽만 있어서 A0에서 실패했습니다. 결과는 `RESULTS.md`에 있습니다.
  - mt7996는 링크마다 `BSS_CHANGED_TXPOWER`를 처리해서 그 링크의 phy SKU를 바꿉니다. 그래서 MLD 링크 하나의 출력만 낮출 수 있습니다.

명령은 다음과 같습니다(radio 0=2.4 GHz, 1=5 GHz, 2=6 GHz).

```sh
iw dev ap-mld0 set txpower fixed 600 radio 2   # 6 GHz 링크만 6 dBm
iw dev ap-mld0 set txpower auto radio 2        # 원래대로
```

이 방법은 AP의 하향(downlink) 신호만 약하게 만듭니다. Mac이 보는 비콘과 데이터 신호가 약해지므로, 단말이 멀어지는 상황을 근사합니다. 상향(uplink)은 Mac의 출력이라 그대로입니다.

### A0. 도구 동작 확인

- `radio 2`만 낮추고 `/sys/kernel/debug/ieee80211/phy0/netdev:ap-mld0/link-*/txpower`를 읽습니다.
  - 합격: link-2만 바뀌고 link-1과 2.4 GHz `phy0.0-ap0`는 그대로입니다.
- `auto`로 되돌린 뒤 23/18/23 dBm으로 돌아오는지 확인합니다.

### A1. 6 GHz 감쇠 시 대역 전환 (5+6, 다운로드)

- 측정: 다운로드 90초, 1초 단위 기록, 5 Hz ping.
- 15초마다 6 GHz 출력을 바꿉니다: 18 → 12 → 6 → 3 → 1 dBm → auto.
- 기록 항목:
  - 1초 처리량
  - ping 손실
  - Mac의 `valid_links`와 `primary`
  - 링크별 rx/tx 바이트(`iw dev ap-mld0 station dump`)
  - `logread`의 연결 해제 여부
- 합격 기준:
  - AP-STA-DISCONNECTED가 없어야 합니다.
  - 0 Mbps인 1초 구간이 없어야 합니다.
  - ping 손실이 1% 미만이어야 합니다.
  - 6 GHz가 약해지면 5 GHz 단독 수준(약 1.9 Gbps)을 유지해야 합니다.
  - auto로 되돌린 뒤 30초 안에 두 링크로 돌아와야 합니다.
- 업로드(`-R` 없이)도 같은 방법으로 측정하고, 각각 3회 반복합니다.

### A2. 5 GHz 감쇠

- A1과 같은 절차로 radio 1의 출력을 낮춥니다(23 → 15 → 8 → 3 → 1 dBm).

### A3. 2.4 GHz 조합에서의 링크 선택

- 2.4+6 조합에서 radio 0의 출력을 1 dBm까지 낮췄을 때 Mac이 primary를 6 GHz로 옮기는지 봅니다.
  - 옮기면: Mac의 링크 선택은 신호 세기를 따릅니다. r60에서 2.4 GHz를 고른 것은 2.4 GHz 비콘 RSSI가 더 강했기 때문입니다.
  - 옮기지 않으면: 2.4 GHz 링크를 계속 고집하는 원인을 AP 쪽 광고(MLD 능력, EML)에서 찾아야 합니다.
- 2.4+5+6 조합에서도 같은 방법으로, Mac이 0x0006(5+6)으로 바뀌는지 봅니다.

### A4. 회귀 확인

- 5+6 기본 구성에서 `.device/mac-wifi-check.sh 1`을 실행합니다.
- 커널 경고, 오프로드 flow 수, 24시간 안정성 확인을 기존과 같이 봅니다.

## r62: 링크를 빼고 넣어도 연결 유지 (upstream 무선 스택 동기화)

upstream main에서 이 동작을 만드는 커밋:

- `21b47bd63f`: 라디오 재시작 전에 MLD 링크 제거를 알립니다.
- `beeab8d647`: 링크가 제거돼도 non-AP MLD의 연결을 유지합니다.
- `1be9a8d1ba`: 제거되는 링크에 있던 association link를 다른 링크로 옮깁니다.
- `3e04ecce`: 제거되는 링크의 단말을 프레임 처리 전에 deauthorize합니다.
- `f37e174443`: PTK 재키잉 M2에서 association link를 허용합니다.
- `3a50215a24`: 타이머가 만료되면 제거된 링크의 데이터를 정리합니다.
- `cf660e88b5`, `24bdd0906b`: Link Reconfiguration으로 링크를 추가하는 경로입니다.
- `0108a88ab5`: ucode를 초기화할 때 `hostapd.interfaces`를 설정합니다(21b47bd63f의 버그 수정).

이 커밋들만 따로 가져올 수는 없습니다.

- `257c0f6bd5`가 hostapd와 mac80211의 nl80211 UAPI 번호를 같이 바꿉니다.
- hostapd와 wifi-scripts에 우리 트리에 없는 커밋이 259개 쌓여 있습니다.
- mac80211 subsys 423–483에는 TTLM, SCS/MSCS, AP Removal Timer(`9abf356d31`)가 들어 있습니다.
- upstream mt76은 `0936617dc5`로 올라가 있어 우리 핀(`639e1287`)보다 83커밋 앞섭니다.

AP Removal Timer를 드라이버가 세는 오프로드는 두 mt76 핀 모두 구현하지 않습니다. 그래서 hostapd의 소프트웨어 타이머 경로로 동작합니다.

빌드 범위:

1. mac80211, hostapd, wifi-scripts, netifd를 upstream main에 맞춥니다. 우리 패치(mac80211 9998·9999·999, hostapd 9998·9999)는 그 위에 다시 적용합니다.
2. mt76을 `0936617dc5`로 올리고 0006–0041 패치를 다시 맞춥니다.
   - 0006/0029(NPU RX), 0008, 0012, 0015는 동작을 바꾸는 패치라 하나씩 확인합니다.
3. 호스트 테스트를 모두 돌립니다(`tests/`, 특히 `test_mt7996_mlo_ps.py`, `test_mt76_npu_rx.py`).

시험 항목:

- B1. 5+6에서 `radio2`를 빼고 `wifi reload`를 실행합니다.
  - 합격: AP-STA-DISCONNECTED가 없고, 비콘에 Reconfiguration ML 요소가 나가고, Mac이 link 1로만 계속 통신하며, 0 Mbps 구간이 1초 이하입니다.
- B2. `radio2`를 다시 넣습니다.
  - macOS가 Link Reconfiguration으로 링크를 다시 추가하는지, 아니면 다시 연결하는지 기록합니다. macOS가 링크 추가를 지원하지 않으면 다시 연결하는 것이 정상입니다.
- B3. 2.4 GHz 문제 확인
  - upstream의 TID-to-link mapping 광고(hostapd 609, mac80211 `c8f1f84c06`)로 데이터 TID를 5/6 GHz에만 매핑해 봅니다.
  - Mac이 2.4 GHz를 primary로 잡아도 처리량이 유지되는지 봅니다.
- B4. r61의 A1–A4를 같은 이미지에서 다시 측정합니다(회귀 확인).
- B5. DFS(9999), NPU RX, 브리지 오프로드, 24시간 안정성을 확인합니다.

## 공통 조건

- Mac의 유선 연결을 끊습니다.
- Tailscale `--accept-routes=false`로 둡니다.
- 시스템 설정의 Wi-Fi 창은 닫습니다.
- 접속한 뒤 40초를 기다립니다. macOS 로밍 스캔 때문입니다(`docs/mlo-r53/JOIN_DIP_20261017.md`).
- 측정 스크립트는 공유기에서 `sh -c '…' &`로 띄웁니다. busybox에는 `nohup`이 없습니다.
- 측정이 끝나면 `radio1 radio2` 구성과 `txpower auto`로 되돌립니다.
