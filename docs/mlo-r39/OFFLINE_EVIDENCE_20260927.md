# Air 기존 BA 기록 및 kernel73 내부 비교 — 2026-09-27

추가 무선 시험·공유기 접속 없이 보존한 로그와 공개 이미지를 조사했다. r39 제품 소스·태그·릴리스 파일은 변경하지 않았다.

## Air BA 가설의 적용 범위를 좁힘

**r29 Air 정상 회차 3개에서 AP가 받은 성공 ADDBA 응답 13건은 모두 timeout=0**이었다. 기존 문서의 포괄적인 “Air timeout 미확인”은 “r32 실패 회차의 timeout 미계측; r29의 기록된 정상 세션은 0”으로 좁혀야 한다. 0이면 해당 세션의 TX aggregation inactivity timer를 켜지 않으므로, 이 13개 협상의 세션에는 r39의 유휴 갱신 누락이 적용되지 않는다. 이는 새 연결인 r32 실패의 timeout까지 같다는 증명이 아니다.

| r29 성공 회차 | 수신 성공 응답 | timeout | 사용자 평균/최저/최고 Mbps |
|---|---:|---|---|
| 실제 peer를 정정한 패킷 회차 | 4 | 모두 0 | 1184 / 890 / 1422 |
| 서버 포트 기준 전체 캡처 | 7 | 모두 0 | 1209 / 1124 / 1255 |
| 화면 잠금 이후 회차 | 2 | 모두 0 | 1156 / 773 / 1411 |

대상은 정정된 `IPHONE_RESULT.json`·`RESULT.md`의 Air이며, 각 수신 응답의 TID와 인접한 해당 MLD의 BAMCU TX BA enable(timeout0/ret0)을 대조했다. 다른 peer와 AP가 보낸 ADDBA 응답을 수신 응답 수에 섞지 않았다. phase의 kernel sequence가 중복되지 않는 것도 확인했다. [원본 해시·행·sequence·TID와 대조 결과](HISTORICAL_BA_EVIDENCE.json)를 공개하며 MAC/IP와 원시 로그는 공개하지 않는다.

### DELBA 네 건은 다운로드 유휴 만료가 아님

선별한 DELBA는 모두 `dir=T act=2 cap=7000 result=38`이다. 실제 BATRACE는 DELBA parameter를 little-endian으로 읽는다. `0x7000`은 TID7·initiator0이며, AP가 이 BA의 수신측이라는 뜻이다. 따라서 업링크 세션에 대한 `QSTA_REQUIRE_SETUP` 기록이다. 현재 mac80211 `rx.c:1475/3398`의 예상 밖 BlockAck 정책 데이터 또는 BAR 경로가 같은 recipient/38 요청을 만들지만, 이 둘 중 어느 입력이었는지는 로그만으로 구별할 수 없다.

반면 TX inactivity 정리의 `agg-tx.c:948–950`은 initiator1·reason37(`QSTA_NOT_USE`)을 보낸다. **reason39가 없다는 사실만으로 TX 만료를 배제하면 안 된다.** 이번 네 건은 송신 방향과 initiator 비트까지 함께 확인했기 때문에 구별한다. TID7 TX 만료의 정상 정리라면 parameter는 `0x7800`이다.

MT7996가 요청 timeout0을 보내도 peer 성공 응답값을 `agg-tx.c:1056–1062`에서 그대로 수용한다. 그러므로 요청0만으로 r39 코드 결함이 도달 불가능하다고 해석하지 않는다. 기록된 Air 성공 응답0과 일반적인 peer의 비영 timeout 응답 가능성은 별개다.

### 남은 계측 한계

BATRACE에는 rate limit이 있으므로 이벤트 부재가 완전한 부재 증명은 아니다. r29 PCAP은 Ethernet/LAN IP·TCP 캡처라 무선 BA frame을 복원할 수 없다. `agg_status`는 per-TID `last_tx`를 출력하지 않는다. r32 실패 회차에는 협상 timeout·BA 이벤트·정확한 앱 멈춤 시각·동시 peer별 TCP 진행이 없다. 따라서 BA 만료, peer PS 정체, NPU worker 정체 사이 원인 순위를 확정할 수 없다. 새 r 버전을 만들거나 firmware를 수정할 근거로 정상 회차의 기록을 실패 원인에 대입하지 않았다.

## 재게시 kernel73 이미지의 실제 내용

[같은 태그 재게시](UPSTREAM_FOLLOWUP.md) 뒤의 이미지 23,335,747바이트를 내려받아 GitHub SHA256 `fbbb6e650c8a477dc8bc7797ed6b98af1d14875e67e0fd914b219f748b9b2fdd`, FIT 3개 payload hash, 보드 metadata를 확인했다. 설치하지 않았다. 비교 기준은 보존한 9월 26일 일반 UBI2이며 **재게시 전 kernel73 원본 bytes는 없어서 두 kernel73 간 차이는 미분석**이다.

- kernel: **7.3-rc4**, GCC16.2.0, libc2.44. 일반 UBI2의 6.18.52/GCC14.4.0/musl1.2.6과 다른 구성이다.
- firmware **12/12개 바이트 동일**: NPU program/data, MT7996 WM/WA/DSP/ROM/EEPROM, regdb, PHY를 포함한다. r39의 NPU program과도 바이트 동일하다.
- 설치 package 220개, module71개다. 일반 UBI2 202개 대비 18개 package 추가, 삭제0개이며 statistics/collectd 및 일부 kernel package 등이 추가됐다.
- wpad/hostapd 버전은 동일하다. 고정 source 비교에서 hostapd·linux-firmware subtree와 mt76 patch 파일도 동일하다. mt76 Makefile의 Airoha Ethernet 의존성 제거는 Ethernet/NPU를 built-in으로 바꾼 설정과 관계된 변경이다. mac80211 추가 patch는 `linux/hex.h` include 호환 수정이다.

[이미지 검사 기록](KERNEL73_IMAGE_VALIDATION.json)에 package 차이·firmware 해시를 남겼다. 새 NPU/MT7996 firmware 또는 새 MT7996 절전 개선이 포함됐다고 해석하지 않는다.

### Airoha 소스 차이의 제한

고정 source는 [kernel73 710dd8fa](https://github.com/OpenWRT-fanboy/OpenW1700k/tree/710dd8fa844785627ac3dd0ddc2799473fa947b5)와 [일반 UBI2 54e453b0](https://github.com/OpenWRT-fanboy/OpenW1700k/tree/54e453b074fc243c33f6b6cc36f6b4e8a176aa45)다.

- [7.3 916 GRO patch](https://github.com/OpenWRT-fanboy/OpenW1700k/blob/710dd8fa844785627ac3dd0ddc2799473fa947b5/target/linux/airoha/patches-7.3/916-02-net-airoha-Implement-HW-GRO-TCP-support.patch)는 공유 QDMA의 LRO 상태와 새 장치의 GRO 설정이 다를 때 open을 `-EBUSY`로 거절하는 조건을 유지한다. 일반 UBI2/r39는 그 조건을 제거한 형태다.
- [7.3 994 공유 patch](https://github.com/OpenWRT-fanboy/OpenW1700k/blob/710dd8fa844785627ac3dd0ddc2799473fa947b5/target/linux/airoha/patches-7.3/994-net-airoha-share-hw-gro-state-across-qdma-users.patch)는 helper의 재진입 보호는 있지만 r39의 `set_features()` 하드웨어 갱신 전 `syncing_gro_features` 조건은 추가하지 않는다. 반복 하드웨어 갱신 가능성은 별도 검토 대상이며 무한 재귀나 Air 정상 전송 정체로 확정하지 않았다.
- AGG_COUNT 상한·SKB_GSO_DODGY·TCP timestamp 유효성 처리는 7.3 patch에도 남는다. 설명 문단 삭제를 코드 보호 삭제로 오인하지 않았다.
- RX31 mask는 다른 patch 문맥에 이미 포함되므로 해당 파일 삭제를 수정 누락으로 세지 않는다. 995 TTL/996 ingress 보호는 활성7.3 patch에 없고 [상위 PPE 원문](https://github.com/torvalds/linux/blob/v7.3-rc4/drivers/net/ethernet/airoha/airoha_ppe.c)에도 같은 변경이 없다. 다만 모든 generic/target patch를 적용한 최종7.3 C는 만들지 않았으므로 동일 효과의 다른 구현까지 배제하지 않는다.

이 차이는 장치 open·feature 변경과 이식 경계에 관한 것이다. 현재 r39보다 Air 순간 멈춤을 개선한다는 근거는 확보하지 못했다. 이번 후속은 **원인 가설의 적용 범위와 새 이미지 내용을 좁힌 조사**이며 최종 해결 판정은 아니다.
