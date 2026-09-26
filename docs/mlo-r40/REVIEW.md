# r40 후보 검토

2026-09-27. **이 문서는 소스 후보와 기존 증거의 검토다. r40 최종 빌드·이미지와 소스 검사는 통과했으며, 설치·실기기 결과는 별도 기록한다. 이 검토는 Air 해결을 입증하지 않는다.**

## 공식 근거와 변경 범위

MediaTek의 2025-09-19 `0130` 패치는 WED 없이 별도 offload를 쓰는 경우 자원 경합을 막기 위해 RED를 켜고 BA 활동 시각도 갱신해야 한다고 설명한다. 실제 변경은 RED 초기화를 항상 활성화하고 BA 갱신의 WED 조건을 제거한다. Airoha NPU나 현재 WM·WA 바이너리의 해시·필요 버전을 명시한 패치는 아니다. r39는 WED 또는 NPU의 BA 갱신을 이미 추가했으며, r40 후보는 RED 초기화만 다룬다. [공식 0130](https://github.com/mediatek/mtk-openwrt-feeds/blob/7ad9c8131527674c94045b436894419a07001835/autobuild/unified/filogic/mac80211/24.10/files/package/kernel/mt76/patches/0130-cp-mtk-mt76-mt7996-enable-RED-and-fresh-agg-timer-no-ma.patch)

[0036](../../package/kernel/mt76/patches/0036-mt7996-initialize-red-for-npu-offload.patch)은 `is_mt7996()`와 `mt76_npu_device_active()`가 모두 참일 때 다음 순서를 실행한다.

1. WM VOW `UNI_VOW_RED_ENABLE(0x18)`에 값 2를 보내고 응답을 기다린다.
2. WA SET `MCU_WA_PARAM_RED(0x0e)`에 값 1을 보낸다.
3. WA SET `RED_CONFIG(0x40)`에 mode 2, TCP offset 200, priority offset 255 및 토큰 예산을 보낸다.

같은 공식 24.10 계열의 `0011`과 `0035`를 기준으로 MT7996의 644바이트 요청 형식(32비트 인자 3개와 body 632바이트)을 유지한다. source 0–2 예산과 네 threshold는 16,384이며, source 3 예산은 `dev->mt76.token_size`다. 현재 NPU host 설정에서는 이 값도 16,384다. 오래된 `0057`의 no-WED source 3 예산 8,192를 복사하지 않는다. [공식 0011](https://github.com/mediatek/mtk-openwrt-feeds/blob/7ad9c8131527674c94045b436894419a07001835/autobuild/unified/filogic/mac80211/24.10/files/package/kernel/mt76/patches/0011-mtk-mt76-add-debug-tools.patch), [공식 0035](https://github.com/mediatek/mtk-openwrt-feeds/blob/7ad9c8131527674c94045b436894419a07001835/autobuild/unified/filogic/mac80211/24.10/files/package/kernel/mt76/patches/0035-mtk-mt76-mt7990-use-device-id-macro-in-internal-debu.patch)

MT7996 이외 장치와 NPU 비활성 경로는 기존 WA RED 값 0 전송을 유지한다. 후보는 MCU 초기화 소스만 변경하며 펌웨어 blob, Ethernet/NPU 드라이버, 토큰 allocator나 token ID 범위를 변경하지 않는다. 최종 이미지의 실제 변경 파일·해시 확인은 별도 빌드 검증 대상이다.

## 응답·토큰 계약의 한계

WM 설정 응답을 기다리는 것과 WA 설정 상태를 읽는 것은 다르다. WA enable과 token config는 응답을 기다리지 않는다. 성공 로그의 `WM ACK, WA commands queued`는 이 차이를 표현하며 실제 RED 활성 상태를 보증하지 않는다. 공식 계열의 `red` getter도 host 캐시를 반환할 뿐이다. 초기화 오류는 반환하지만 이미 수락된 WM 설정이나 전송된 WA 명령을 원자적으로 되돌리는 기능은 없다.

기존 vendor NPU 프로그램의 SHA256 `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643`에서 선택한 32개 명령을 다시 디스어셈블했다. `0x8400eea6/eeb2` 초기화는 TXP v2에 해당하고, `0x8400f386–f3b6`의 fast TX 구성 산술을 metadata 128개 × route 16개로 투영하면 공식 `HIF_TXP_SRC` bits 27:26은 모두 0이다. 이 검사는 선택 명령의 바이트·산술 대조이며 범위 사이의 모든 분기·레지스터 수명이나 실제 장비 실행을 검증하지 않는다.

**HIF_TXP_SRC=0이 RED의 `token_per_src[0]`에 대응한다는 WM/WA 소비자 계약은 없다.** NPU token pool 8,192개와 host token ID 8,192–24,575의 분리는 확인했지만, RED 예산 16,384의 의미·적합성을 여기서 증명할 수 없다. 현재 WM·WA는 암호화 다운로드 영역을 사용하므로 평문 코드에서 해당 소비자를 확인했다고 주장하지 않는다. 상세 근거와 바이너리 해시는 [r39 RED 계약 기록](../mlo-r39/RED_CONTRACT_20260927.md)을 따른다.

## 기준 시험과 판단

아래 값은 모두 r40 적용 전 r39에서 측정한 Mac의 60초 TCP 다운로드다. 평균은 수신 합계, 최저는 클라이언트 1초 수신 표본이며 단위는 Mbps다.

| 기록 / 전달 경로 / Wi-Fi 설정 화면 | 평균 | 최저 | 관측 |
| --- | ---: | ---: | --- |
| 앞선 기록 / CPU / 열림 | 912 | 50 | 반복 저하, 재전송 654회 |
| 앞선 기록 / PPE / 열림 | 1,281 | 45 | 반복 저하, 재전송 12,336회 |
| 앞선 기록 / PPE / 닫힘 | 1,971 | 1,787 | 재전송 1,325회 |
| 새 기준 / PPE / 닫힘 | 1,824 | 96 | 500Mbps 미만 두 표본은 시작 직후 2초, 재전송 1,039회 |
| 새 기준 / PPE / 열림 | 1,957 | 1,857 | 반복 저하 없음, 재전송 1,419회 |

새 기준 두 회차에는 수신량 0인 1초 표본이 없었다. 앞선 가속·열림 기록의 약 한 MSS cwnd와 개별 스트림 Transfer=0은 서로 다른 스트림·시점이다. 재전송 합계는 무선 손실 수나 RED 드롭 수가 아니다. [송신 TCP 해석](../mlo-r39/RED_CONTRACT_20260927.md), [전달 경로·관측 조건](../mlo-r39/MAC_PATH_FOLLOWUP_20260927.md)

변경 전 새 기준에서 반복 저하가 재현되지 않았으므로 설정 화면 열림, RED, NPU, TCP 혼잡 윈도우 중 하나를 확정 원인으로 지정할 수 없다. r40 이후 정상 결과만으로 개선 효과를 확정해서도 안 된다. 소스 후보는 공식 non-WED 초기화 근거를 좁게 적용하는 실험이며, 실제 WM/WA 적용 상태·부팅 및 복구 안정성·회귀 여부는 별도 확인이 필요하다.
