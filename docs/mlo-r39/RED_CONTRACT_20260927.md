# r39 — TXFREE RED 의미와 서버 TCP 기록 재검토

2026-09-27. **보존한 Mac 시험을 다시 분석한 기록이며, 새 펌웨어나 새 무선 시험 결과가 아니다.** r39 이미지·태그·장비 설정은 유지했다. 기존 Air 순간 멈춤의 원인은 여전히 미확정이다.

## 확인한 사실

MediaTek 공식 MT7996 패치 `0057-mtk-mt76-add-random-early-drop-support.patch`는 `mt7996_mac_tx_free()`의 `MT_TXFREE_INFO_STAT == 2`를 `red_drop`으로 집계하고 `Tx RED drop`으로 표시한다. 현재 r39의 TXFREE HEADER bit 30 / STAT bits 29:28과 맞는다. **2023년 작성된 기존 패치를 이번에 확인한 것이며, 새로 배포된 수정은 아니다.** [공식 고정 소스](https://github.com/mediatek/mtk-openwrt-feeds/blob/7ad9c8131527674c94045b436894419a07001835/autobuild/autobuild_5.4_mac80211_release/mt7988_wifi7_mac80211_mlo/package/kernel/mt76/patches/0057-mtk-mt76-add-random-early-drop-support.patch)

따라서 이전 보고서의 raw status 2에 **벤더가 RED 드롭으로 분류한 값**이라는 의미를 추가할 수 있다. 다만 HEADER 보고 횟수이므로 TCP 패킷 손실 개수와 같지 않으며, PS·UAPSD·EMLSR·타임아웃 중 어느 것이 원인인지는 이 값만으로 알 수 없다. 별도의 TXS PS/timeout 비트를 TXFREE 상태값에 대입하지 않는다.

보존된 60초 다운로드의 Linux 서버 `server_output_text`를 4개 실제 연결과 대응해 검사했다. 주소·포트·쿠키는 공개 자료에서 제외했다. 아래 cwnd는 수신 윈도우가 아닌 **송신 TCP 혼잡 윈도우**다.

| 경로 / Mac Wi-Fi 설정 화면 | 평균 수신 Mbps | 서버 재전송 합계 | 개별 스트림 최저 cwnd | 개별 스트림 1초 Transfer=0 |
| --- | ---: | ---: | ---: | ---: |
| CPU 전달 / 열림 | 912 | 654 | 127 KiB | 0 / 240 |
| PPE 가속 / 열림 | 1,281 | 12,336 | 1.41 KiB | 1 / 240 |
| PPE 가속 / 닫힘 | 1,971 | 1,325 | 752 KiB | 0 / 240 |

- 가속·열림의 최소 cwnd는 5–6초의 서버 스트림 8이며 iperf가 기록한 기본 MSS와 비교하면 약 한 MSS 크기다. 패킷에서 실제 MSS 협상을 확인한 것은 아니다. Transfer=0은 **다른 스트림 5의 6–7초** 표본이다. 해당 표본에도 재전송이 있어 실제 wire 패킷이 전혀 없었다는 뜻이 아니다. 네 스트림이 동시에 Transfer=0인 1초 구간은 세 회차 모두 없었다.
- CPU·열림의 첫 저하(7–11초)는 재전송 합계 2회, 해당 구간 최저 cwnd 140 KiB였다. RED 상태 증가도 0이었다. 1 MSS 수준의 혼잡 윈도우 축소나 관측된 RED 드롭은 주기적 속도 저하의 필수 조건이 아니다.
- 클라이언트 수신과 서버 송신의 상대 1초 표본은 지연 0에서 가장 가까웠다. 이는 절대 시계 동기화나 패킷별 인과를 입증하지 않는다. RTT·RTO·ACK 누락·수신 윈도우·무선 재시도를 이 출력만으로 복원할 수 없다.

이 자료는 설정 화면 열림 때 가속 경로에서 재전송과 cwnd 축소가 함께 관측됐다는 근거다. RED가 원인인지, 단말이 전송을 받을 수 없는 동안 생긴 결과인지, 원래 Air 문제와 같은 현상인지는 아직 구분하지 못한다. CPU 회차도 전역 NPU는 켜져 있었다. 시험 조건·추가 진단 부하·유선 검증은 [이전 후속 기록](MAC_PATH_FOLLOWUP_20260927.md)을 따른다.

## 현재 드라이버와 벤더 RED 초기화의 차이

현재 prepared `mt7996/mcu.c`는 WA `MCU_WA_PARAM_RED(0x0e), 0, 0`을 보낸다. 전송 함수는 응답을 기다리지 않으므로 반환값 0이 펌웨어 내부 RED 비활성 상태의 조회 성공을 뜻하지 않는다.

공식 패치는 WM VOW `UNI_VOW_RED_ENABLE(0x18)`과 WA RED enable을 함께 설정하고, 활성화할 때 WA `RED_CONFIG(0x40)`의 토큰 예산·임계값까지 보낸다. 그러나 WED용 초기화를 NPU에 그대로 적용할 근거는 없다. WED offload enable 시 host token pool을 8,192개로 축소하지만 현재 NPU 경로는 host 시작 ID 8,192 / pool 크기 16,384를 사용한다. 소스 인덱스·임계값의 펌웨어 의미가 확보되지 않아 이를 잘못된 토큰 범위라고 판정하지 않는다.

명시적인 WM 설정 유무는 **소스 차이**로 확인했지만, 현 펌웨어의 기본값이나 WA 명령과의 연동 계약은 확인하지 못했다. 오래된 `0057`의 `red` debugfs는 쓰기 전용이다. 뒤에서 확인한 24.10 계열에는 getter가 있지만 호스트의 `dev->red_enable` 캐시를 반환하며, 캐시는 WA 전송 전에 갱신된다. 어느 쪽도 펌웨어 내부 상태 readback이 아니다. 일반 QUERY enum만 보고 RED 조회 명령을 만들어 보내거나, RED를 강제로 끄지 않았다.

추가로 MediaTek의 2025-09-19 패치 `0130-cp-mtk-mt76-mt7996-enable-RED-and-fresh-agg-timer-no-ma.patch`를 확인했다. 이 패치는 **WED 없이 별도 offload를 쓰면 host CPU 경로를 지나지 않으므로 RED를 활성화하고 BA 활동 시각을 갱신해야 한다**고 설명한다. BA 갱신의 WED 조건을 제거하고 `mt7996_mcu_red_config(dev, true)`로 바꾼다. [공식 고정 소스](https://github.com/mediatek/mtk-openwrt-feeds/blob/7ad9c8131527674c94045b436894419a07001835/autobuild/unified/filogic/mac80211/24.10/files/package/kernel/mt76/patches/0130-cp-mtk-mt76-mt7996-enable-RED-and-fresh-agg-timer-no-ma.patch)

r39의 WED 또는 NPU 경로 BA 갱신 수정은 이 방향과 일치하지만 같은 코드 전체를 적용한 것은 아니다. RED 초기화는 r39에 포함되지 않았다. 이 문서는 **RED를 끄는 수정 대신 non-WED offload의 RED 초기화 누락 가능성을 후속 검토할 공식 근거**가 된다. 다만 해당 패치가 Airoha NPU나 현재 WM·WA 해시를 명시하지 않으므로 호환성·개선 효과를 확정하지 않는다. 이 패치도 2026-09-27 신규 발표가 아니라 이번 조사에서 추가로 발견한 기존 패치다.

`0130`이 실제 호출하는 같은 24.10 계열의 의존 구현도 확인했다. `0011`은 WM ACK → 호스트 상태 캐시 → WA enable → WA token config 순서이며, 이후 `0035`는 MT7996의 source 3 토큰 예산을 `dev->mt76.token_size`로 바꾼다. 나머지 세 source 예산과 네 임계값은 16,384다. MT7996의 WA `0x40` 형식은 3개 32비트 인자와 632바이트 body로 유지된다. **옛 `0057`의 no-WED 예산 8,192를 그대로 복사하는 구현은 이 의존 계열과도 다르다.** 이로써 적용 후보의 호출 순서·형식은 좁혔지만 source 3과 Airoha NPU 토큰의 의미가 같다고 확인한 것은 아니다. [공식 `0011` 구현](https://github.com/mediatek/mtk-openwrt-feeds/blob/7ad9c8131527674c94045b436894419a07001835/autobuild/unified/filogic/mac80211/24.10/files/package/kernel/mt76/patches/0011-mtk-mt76-add-debug-tools.patch), [공식 `0035` 변경](https://github.com/mediatek/mtk-openwrt-feeds/blob/7ad9c8131527674c94045b436894419a07001835/autobuild/unified/filogic/mac80211/24.10/files/package/kernel/mt76/patches/0035-mtk-mt76-mt7990-use-device-id-macro-in-internal-debu.patch)

## 실제 r39 WM·WA 펌웨어 확인 범위

기존 mt76 loader 형식 검사기를 재사용해 r39 검증 이미지의 원본 파일을 읽었다.

| 파일 | 크기 | trailer build date | 암호화 다운로드 표시 영역 |
| --- | ---: | --- | ---: |
| `mt7996_wm.bin` | 2,666,168 bytes | `20260721003035` | 9 / 9 |
| `mt7996_wa.bin` | 510,064 bytes | `20260721002917` | 3 / 3 |

- WM SHA256: `99020e57ff91fdee09b833f9d35f97ff70722d0ef32fa8b02f70c8d3c6f95592`
- WA SHA256: `06106c918866c7ae3da47b27223da17030212a1a4adcb5c23871325291d06448`

각 영역의 `FW_FEATURE_SET_ENCRYPT`가 실제 loader의 암호화 다운로드 모드에 연결된다. 평문 ELF·심볼이나 의미 있는 RED 제어 문자열을 찾지 못했으며, 암호화된 바이트를 역어셈블해 WA 명령 처리 함수를 확인했다고 주장하지 않는다. 영역 길이·파일 범위는 확인했지만 trailer CRC는 검증하지 않았다. 이는 앞서 별도로 역어셈블한 **Airoha NPU 바이너리와 구분되는 MT7996 WM·WA 파일**이다.

## 검증 자료와 다음 판단 기준

[공개 수치와 입력·소스 해시](RED_CONTRACT_20260927.json), [서버 기록 검사기](check-sender.py)를 함께 보존했다. 입력 원본은 단말 식별 정보를 포함하므로 비공개로 유지한다. 검사기는 아래처럼 보존된 세 시험 폴더를 가진 디렉터리에 실행한다.

```sh
python3 check-sender.py /path/to/private-trials --output new-sender-evidence.json
```

설정을 바꾸기 전 필요한 근거는 현재 WM·WA 해시에 대응하는 RED 상태 조회·명령 응답 계약, 또는 실제 저하 시점의 송신 측 TCP와 무선 상태가 겹치는 기록이다. 기존 정상 재연결 검증을 원래 Air 절전 멈춤의 해결 증거로 대체하지 않는다. 이번 확인 후에도 유선 관리 연결과 2.5Gbps 서버 링크는 정상이었고, 진단 옵션은 꺼져 있으며 임시 가속 우회 규칙은 남아 있지 않았다.
