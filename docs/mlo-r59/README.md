# r59 — 보안 갱신(커널 6.18.59, OpenSSL 3.5.9, rpcd·procd·ubus)

r58 위에 CVE 검토(2026-10-30)에서 나온 보안 갱신을 넣은 버전입니다. mt76, hostapd, 무선·NPU 펌웨어는 r58과 같습니다.
2026-10-30 실제 장치에 설치해 확인했습니다. MLO 간헐 멈춤의 해결 여부는 바뀌지 않았습니다.

## 바뀐 점

- 커널 6.18.55 → 6.18.59. 6.18.56~59 stable의 네트워크 수정(ipv4 checksum_start 검증, inet_opt·page_pool·tcp
  getsockopt·net/sched UAF, AF_PACKET TX_RING 오버플로, nft_flow_offload 참조 누수, 브리지 VLAN untag의 num_encaps
  underflow 등)을 받습니다. upstream OpenWrt는 아직 6.18.55입니다.
  - `438`(spinand QE)은 6.18.59에 들어 있어 뺐습니다.
  - `706-03`과 `675-02`를 6.18.59의 untag 수정 위에 다시 맞췄습니다. `706-03`은 VLAN 없는 untag에서 오프로드하지 않고,
    `675-02`는 r58처럼 이를 허용합니다(경고 없이).
  - `675-03`은 `skb_ipv6_payload_len()` 도우미에 맞췄습니다.
  - bridge-flow-offload가 `6.18.59-w1700k-mlo-r32`를 허용합니다. `test_bridge_ttl.py`,
    `test_bridge_conntrack_ownership.py`, `test_bridge_fdb_cleanup.py`, `test_bridge_flow_offload.py`가 6.18.59 트리에서
    통과합니다.
- OpenSSL 3.5.8 → 3.5.9: CVE 13건(High 1건 CVE-2026-84782는 DTLS 전용). upstream `ATOMIC64_DEPENDS`를 함께 가져왔습니다.
- rpcd 2026-10-28: 비 root ubus 호출자에게도 세션 ACL 적용, 세션 ID를 런타임 파일 이름에 쓰지 않음. 이 버전이 요구하는
  ubus 2026-10-28을 함께 넣었고(libubus ABI 20261028), ubus를 쓰는 패키지를 다시 빌드했습니다. 포크의 STATUS_BREAK
  패치는 upstream이 처리해 뺐습니다.
- procd 2026-10-18: ujail 격리 강화, hotplug drop-in 디렉터리, audio 그룹의 audio-support 분리.
- 6.18.57 이후 빌드 수정: NFS 보안 RPC 모듈에 krb5·krb5enc 포함, Intel ice용 `kmod-libeth-xdp` 추가, backports의
  `sockaddr_unsized` 중복 정의 제거(mac80211 PKG_RELEASE 11). PF_RING 9.2.0은 6.18.57에서 빌드되지 않아
  `kmod-pf-ring`을 설정에서 뺐습니다(이미지에는 원래 없음).
- 쓸 수 없게 된 `tests/test_dsa_fdb_delete.py`(r58에서 뺀 `9999-z7`을 적용)를 지웠습니다.

## 실기기 확인 (2026-10-30)

| 항목 | 결과 |
|---|---|
| 설치 | r58에서 설정 유지, `sysupgrade -T` "Signature check OK", 약 100초 만에 접속 |
| 부팅 | 커널 6.18.59, 커널 경고 0, MLO 5 GHz·6 GHz 160 MHz, 주요 서비스 모두 동작 |
| 패키지 | libopenssl3 3.5.9, rpcd 2026-10-28, procd 2026-10-18, ubus 2026-10-28 |
| 브리지 오프로드 | 켜짐(lan2 ↔ ap-mld0), fw4 flowtable 구성은 r58과 같음 |
| LuCI·rpcd | 로그인 페이지 정상, 익명 ubus 세션 확인 동작, 권한 필요한 호출은 거부 |
| Mac 재연결 1회 | MLO 두 링크(valid_links 0x0006, primary 6 GHz) |
| Mac 무선(iperf3 4흐름 30초) | 하향 1,983·1,990·1,988 Mbps, 상향 1,830·1,805 Mbps, 500 Mbps 미만 구간 0 |

## 알려진 제약

r58과 같습니다([r58 기록](../mlo-r58/README.md)).
