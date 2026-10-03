# W1700K2 OpenWrt / MLO 인계서 — 2026-10-03

이 문서는 9월 8일부터 진행한 원인 조사·수정·빌드·실기기 검증을 Claude가 이어받기 위한 시작점이다. **평균 속도 제한은 상당 부분 개선했지만, 간헐적인 MLO 멈춤의 원인은 아직 확정하지 못했다.** 이전 문서의 “현재”, “미설치”, “다음 단계”는 작성 당시 상태다. 아래 후속 이력과 날짜를 함께 읽어야 한다.

10월 3일에는 로컬 파일과 GitHub를 확인하고 공개 누락분을 정리했다. 공유기·클라이언트의 실행 상태를 다시 조회하거나 새 펌웨어를 설치하지 않았다. Matter는 사용자가 해결했다고 알려 이번 인계 범위에서 제외했다.

## 1. 새 담당자가 먼저 알아야 할 결론

1. **CPU / 브리지 가속 문제는 실측으로 확인했다.** LAN→Wi-Fi 전달이 CPU 경로에 머무르면서 약 1.1–1.3Gbps에 제한되던 조건에서, 하드웨어 가속을 적용하자 약 1.9–2.0Gbps와 낮은 CPU 사용률을 확인했다. 단순 CPU affinity 변경보다 효과가 컸다.
2. **가속을 켜기만 하면 정확성 문제가 있었다.** L2 브리지인데 IPv4 TTL을 64→63으로 줄이는 것을 수신단에서 확인했다. r30의 software fast path 및 Airoha PPE KEEP_TTL 수정 후 제한된 비교 시험에서 TTL64 보존을 검증했다.
3. **드라이버·NPU까지 실제로 조사하고 수정했다.** mt76/MT7996, mac80211, hostapd, Airoha QDMA/PPE/NPU host driver, 설치된 RV32 NPU 바이너리의 명령어와 호출 경로를 검토했다. FDK 문서만 읽고 끝낸 작업이 아니다.
4. **원래 Air의 절전 복귀 후 간헐 멈춤은 미해결이다.** r32에서도 5분 시험 `1914 / 0 / 2041Mbps`와 짧은 멈춤이 있었다. r43 Mac 시험에도 저하 회차와 같은 연결의 정상 회차가 모두 있다.
5. **r43은 실험용이다.** 정확한 vendor NPU program/data 쌍에만 부팅 전 DRAM 실행 사본 4바이트 가드를 적용한다. 원본 파일이 같다고 “실행 펌웨어는 바꾸지 않았다”고 설명하면 틀린다. 가드 실행 빈도 및 원래 증상과의 인과는 미확인이다.
6. **다음 분별력 있는 증거는 양단 캡처다.** 서버에서 ACK가 끊긴 시각과 Mac에서 데이터/ACK가 관측된 시각을 맞춰 순방향과 역방향 지연을 구분한다. 유효한 실제 양단 시험은 아직 완료하지 못했고, 10월 3일 캡처 모의 시험도 하나 실패하여 도구 종료 경로 재검증이 먼저 필요하다.

## 2. 저장소·버전·실물의 기준

| 항목 | 기준 및 주의 |
|---|---|
| 공개 저장소 | [VultaV/OpenW1700k](https://github.com/VultaV/OpenW1700k) |
| 계속 작업할 브랜치 | `codex/mlo-r30-bridge-offload`; push remote는 `fork` |
| 원본 upstream | `OpenWRT-fanboy/OpenW1700k`; remote `origin`으로 사용자 작업을 push하지 않는다 |
| 로컬 공개 checkout | 작업 폴더의 `publish-mlo-r29/` — 이름은 r29지만 r43까지 포함한다 |
| 10월 3일 업로드 전 HEAD | `f35329248598735d4fb3927412e8d70410d05442`, 원격과 일치 |
| GitHub 기본 브랜치 | 10월 3일 조회 시 `codex/mlo-r29-progress-20260921`; 기본 clone 뒤 최신 브랜치를 명시적으로 선택해야 한다 |
| 최신 공개 커스텀 이미지 | [mlo-r43-20260927](https://github.com/VultaV/OpenW1700k/releases/tag/mlo-r43-20260927), prerelease |
| r43 태그의 소스 커밋 | `f5b30bd929cd13d62034a9915b77e71bd75d1f98`; 이후 분석 문서는 브랜치에 누적 |
| 원본 source / mt76 | `6d74443bce54df63f6d877040d406cdbcfc16f81` / `01367e60db433534ad0aa3d3b6c886de8cb7d44c` |
| 커널 source / module ABI | `6.18.44` / `6.18.44-w1700k-mlo-r32` |
| 보드 | Gemtek W1700K2, Airoha AN7581, MT7996E, UBI2 프로필 |
| 마지막 설치 검증 | r43, 9월 27일. 10월 3일 현재 장비 상태를 재검증한 것은 아님 |

`w1700k/builds`는 배포/자동화 출발점이었다. **현재 이미지는 fastbuild 완성 이미지를 변형한 것이 아니라 OpenWRT-fanboy/OpenW1700k source를 로컬 빌드한 결과다.** fastbuild fork와 이 source fork를 혼동하지 않는다. 최신 upstream 전체 rebase도 하지 않았다. 필요한 수정만 선택 검토/백포트했다.

r43 이미지:

```text
openwrt-ubi2-mlo-npu-zero-budget-r43-20260927-tailscale-r36182-6d74443bce-airoha-an7581-gemtek_w1700k-ubi-squashfs-sysupgrade.itb
bytes: 30290794
sha256: 562c6bae2f23a2bce0403a0a55f483d1ba49af479a3eac7cec824615dcfab4f2
```

## 3. 사용자가 정한 작업 방식

- 원래 요청은 “MLO 연결은 되지만 불안정하고 단일 링크보다 느린 문제를 드라이버·펌웨어 수준까지 찾아 해결”하는 것이다. 설정 조정이나 빌드 성공만으로 종료하지 않는다.
- 이후 반복적인 Air 실물 시험 부담을 줄이고 **Mac 무선 시험을 주로 사용**하도록 요청했다. 원래 Air 증상의 해결 판정은 별도이며, Air 시험을 반복해서 당연히 요청하지 않는다.
- iPhone 18 Pro 회차는 사용자 정정에 따라 참고 자료로만 남긴다. 주 판정 단말은 iPhone Air다. OS/칩셋이 원인이라고 확인한 것은 아니다.
- 평상시 유선 LAN은 유지한다. 펌웨어 설치·복구 재부팅 중의 일시 중단은 이전 세션에서 허용했고, 설치 때 인터넷은 사용자 핫스팟을 이용할 수 있다. 현재 유선 경로와 복구 수단을 먼저 확인한다.
- **r 버전이 증가할 때마다** source·태그·검증된 firmware·SHA256·한국어 개선 사항을 GitHub prerelease에 올린다. 목표 전체가 끝날 때까지 미루지 않는다. 저장소 `AGENTS.md`를 따른다.
- 비밀번호, 토큰, 설정 백업, Tailscale identity, 원시 패킷, 단말 식별자 목록은 공개하지 않는다. 자격 증명은 사용자와 별도로 처리한다.
- 로컬 작업 폴더는 `openwrt`로 통합했다. 예전 `openwrt.nosync`나 다른 checkout을 최신 빌드 기준으로 삼지 않는다.
- 사용자는 불필요한 대용량 중복 파일 정리를 요청했다. 고유 증거·실제 빌드 디스크·shadow·복구 백업을 잔해로 오인해서 삭제하지 않는다.

## 4. 버전별 작업 이력

초기 상세 기록은 로컬 `artifacts/`에 남아 있다. r29 이후 공개 자료의 시작점은 [r29](mlo-r29/README.md), [r30 현재 기록](mlo-r30/README.md), [r30–32 시간순 기록](mlo-r30/HISTORY.md)이다.

| 버전 | 변경 또는 시험 | 판단 / 뒤집힌 가설 |
|---|---|---|
| 초기 수정본(9/8–9/12) | CPU steering, NPU 불완전 RX chain·fragmented 제어 packet 처리, AQL 이후 TXQ wake, MLO UI/CGI·빌드 수정 | 기존 primary/secondary 선택 0007은 firmware MLD 비동기화 위험으로 철회 |
| r4–r5 | 링크별 PS 진단, rate control이 inactive default VIF PHY를 참조하는 문제 수정 | 처리량 변동은 계속됨 |
| r6 | 빌드 시 Wi-Fi NPU 비활성 A/B | MLO 저하 유지. runtime NPU reset/unbind 시험이 아님 |
| r7 | EML/TID·링크 진단 | 단일 링크 대비 저하를 TID/primary PS 하나로 설명 못함 |
| r8–r9 | 선택 단말 NSTR, 공식 구형 MT7996 firmware 비교 | 확정 개선 없음 |
| r10–r13 | 선택 peer PS 진단 → 두 링크 PS로 공유 TXQ gate 판단 → NPU 재활성 → 통합 | 한 링크 awake면 이용하는 수정. 강제 deauth 뒤 재연결/간헐 정체는 남음 |
| r14 | BA teardown MCU 진단 | 원인 증거 수집 |
| r15 | upstream disassoc→ALTX 변경 | 실물 재연결 회귀로 철회하고 r14 복원 |
| r16–r17 | 관리 frame FL/DIS_MAT 비교, hostapd unknown-station의 link-ID 보존 | 유휴 재연결 개선, 장기 전송 정체는 별개 |
| r18 | PS 수정 위 NSTR 재시험 | 793.75→808.31Mbps였으나 복귀 BA 실패·조건 불일치로 채택 안 함 |
| r19 | 만료 SA-Query/PMF MLD의 이전 association을 새 partner link 추가 전에 정리 | stale partner, 단일 링크 fallback, BA65539 경로 수정 |
| r20 | 초기 frequency 0/상속 band 상태의 링크에도 DFS 상태 전달 | 5GHz AP 시작 실패 실물 수정; MLO stall 해결은 아님 |
| r21–r22 | 링크별 TXS/TXFREE/error flags 진단 | `iw`의 MLO retry=0을 정상 증거로 쓸 수 없음 |
| r23 | awake WCID 강제 선택 OFF/ON/OFF | 평균 869→510→838Mbps로 ON 악화. 기본 OFF 유지 |
| r24–r27 | 송신 WCID·failed test header·BA·PS trace 보강 | 상세 추적 기본 OFF. TX status/retry를 손실률로 직접 해석하지 않음 |
| r28 | MT7996 firmware 20260721→20260311 비교 | AWDL 관련 loss 유지. r27/20260721로 복원 |
| r29 | NPU RX DMA/meta 먼저 기록 후 `dma_wmb()`·ownership 게시 | 누적 source/도구/시험 기록 공개. 원인 입증과는 별개 |
| r30 | bridge conntrack 소유권, software/PPE KEEP_TTL, kernel/module ABI 검증 | 처리량·CPU 및 IPv4 TTL 보존 실증 |
| r31 | bridge-flow-offload 1.0-r2를 이미지에 통합 | 전체 이미지 빌드/공개, 개별 실설치 안 함 |
| r32 | FDB 세대별 flow cleanup, PPE 최신 규칙·slot ownership/reuse·L2 tracking | 실설치. Air 절전 복귀 멈춤 재현 |
| r33 | 가속 패키지가 r30 ABI만 허용하던 오류 수정 | r32 장비에 패키지 별도 설치·실측. r33 전체 이미지 부팅은 아님 |
| r34 | active link selector·WCID 실패 반환, NPU watchdog 수명, LuCI updater 재현/빈 결과 처리 | 전체 검토 F02/F03/N01/F09/F10 수정 |
| r35 | link change 뒤 TXQ 재예약, forward path 동일 primary snapshot·RCU·active link 확인 | 구조적 경계 보완 |
| r36 | NPU TXWI/address → barrier → DONE 게시 순서 | host NPU TX descriptor 수정 |
| r37 | mailbox timeout 뒤 pending coherent request 덮어쓰기 방지 | firmware 취소로 오인하지 않고 EBUSY/오류 보존 |
| r38 | PPE SRAM init 오류를 variable shadowing으로 무시하던 문제 | 오류 전파 수정 |
| r39 | NPU TXS 수신 시 BA activity 갱신 | r34–38 개별 이미지 미설치, 누적 r39 실설치 |
| r40 | non-WED용 RED 초기화를 NPU에 좁게 적용 | 실험 후보. WA queued 응답은 내부 설정 readback 아님 |
| r41 | link activation 실패 rollback 뒤 backlog TXQ 재예약 | Mac 연결 초기 저하 남음 |
| r42 | PS trace 한도 128→1024/5초 | 동작 수정이 아닌 진단 확장 |
| r43 | NPU zero-budget 부팅 전 DRAM 4바이트 guard | 설치·기본 전달 확인, stall 인과 및 개선 미확정 |

각 r34–43의 구체적인 source·검증은 `docs/mlo-rXX/README.md`, `BUILD_RESULT.json`, `build-manifest.json`, `docs/releases/`가 우선이다. r30 이미지는 r31의 통합 이력과 구분하며 존재하지 않는 독립 r30 release를 가정하지 않는다.

## 5. 실측으로 확인한 개선과 남은 현상

기본 시험은 2.5GbE Linux 서버↔무선 단말의 iperf3 TCP download, 4 streams다. Air는 같은 위치에서 5분, 화면 켬, 미러링 끔을 기준으로 했다. 표의 Air 수치는 사용자가 보고한 평균/최저/최고이며 Mac의 interval 수치와 수집 방식이 다르다. MLO는 SSID 이름이 아니라 실제 5+6GHz 두 링크 `0x6`으로 확인했다.

| 시험 | 평균 / 최저 / 최고 Mbps | 해석 |
|---|---|---|
| r29 Air MLO | 1209 / 1124 / 1255 | 전체 4흐름 300초, ACK 진행 공백 >250ms 없음 |
| r29 Air 절전 복귀 | 1156 / 773 / 1411 | 그 회차 정상; 모든 sleep/wake 해결 증거 아님 |
| r29 Air single6 | 1112 / 705 / 1212 | 가속 개선 전 기준 |
| r30 Air MLO | 1963 / 1806 / 2020 | 멈춤 없음 |
| r30 Air single6 재시험 | 1993 / 1761 / 2047 | 멈춤 없음 |
| r32 Air MLO | 1979 / 1784 / 2035 | 새 연결 정상 |
| r32 Air 절전 복귀 | 1914 / 0 / 2041 | 사용자 짧은 멈춤 확인: 미해결 증거 |
| r32 Air single6 절전 복귀 | 1860 / 410 / 2034 | 속도만 낮아지고 멈춤 없음 |
| r32 Air PS 진단 복귀 | 1715 / 1336 / 1987 | 멈춤 없음; 동일 실패 재현 안 됨 |
| r43 Mac 저하 60초 | 평균 1135.767, 1초 zero 1개 | 서버 네 흐름 ACK가 함께 최대 1209.444ms 끊김 |
| 같은 r43 연결 후속 60초 | 1962.077 / 1883.746 / 1997.526 | 0구간·공통 ACK 공백 >100ms 모두 0 |
| 이후 trace OFF 20초 | 평균 1918.906 | 무멈춤, 별도 회차 |

### CPU와 TTL의 근거

- TX worker를 Wi-Fi NAPI와 다른 CPU로 나누자 60초 반복 평균 +16.1%, 300초 한 쌍 +5.0%였다. 최저 속도·재전송의 일관된 개선은 없었으므로 고정 개선율이나 안정성 효과를 주장하지 않는다.
- r30 같은 association의 가속 ON/OFF/ON: **1854.34 / 1392.03 / 1956.28Mbps**, 부하 구간 4코어 평균 CPU **6.76 / 63.36 / 6.89%**. 실제 네 데이터 flow의 HW_OFFLOAD/PPE BND 확인이 있다.
- 가속 전 TTL64, 결함 있는 가속 후 TTL63을 실제 수신단에서 확인했다. 수정 후 baseline/software/hardware 세 조건의 전체 208,638 capture records에서 모든 해당 data TTL64, 캡처 drop 0, IPv4 header checksum 오류 0이었다.
- 이 TTL 검사는 8초·100Mbps·IPv4 reverse TCP의 제한된 결과다. IPv6 hop limit, 일반 routing, VLAN, 모든 packet의 하드웨어 처리까지 검증한 것은 아니다.
- 최초 복구 launcher는 공유기에 없는 `nohup` 때문에 실제 실행되지 않았다. 그 사실을 기록 정정했고 이후 `setsid`, 자식 identity/readiness/survival 검사를 사용했다. 과거 측정값은 유효하지만 최초 복구 준비를 통과했다고 세면 안 된다.

### ACK / PS 해석의 경계

r43 저하 회차 서버 캡처 1,728,003 records(drop 0)에서 네 흐름 공통 ACK 공백 >100ms가 108개였다. 최장 공백에서는 네 TCP 모두 `cwnd=1`, `backoff=1`, 수신 zero-window는 없고 서버 CPU도 낮았다. 후속 정상 회차 1,684,407 records(drop 0)에는 해당 공백이 없었다.

짧은 103개 공백의 서버 도착 간격 중앙값은 약 138ms인데 TCP TSval 증가 중앙값은 약 2ticks였다. 반면 최장 1.209초 공백에서는 TSval도 1220–1222ticks 증가했다. 두 패턴을 하나의 원인으로 일반화하지 않는다. TSval은 실제 RF 송신 시각이나 정확한 생성 시각이 아니다.

Mac 검색/AWDL 동작과 저하가 겹친 사례는 있으나, 정상 회차에도 검색이 있었다. r42의 host PS gate 점유와 저하가 상당 부분 겹쳤지만, 가속된 packet마다 host gate를 통과하는 것이 아니다. “gate가 풀린 뒤 수초 동안 깨어나지 못했다”는 증거도 확보되지 않았다. 자세한 자료: [r42 wake timing](mlo-r42/WAKE_TIMING.md), [r43 재시험](mlo-r43/REPEAT_RESULT.md), [정상 비교](mlo-r43/PS_REPEAT_RESULT.md), [ACK 분석](mlo-r43/ACK_TIMESTAMPS.md).

## 6. NPU 펌웨어 분석의 범위

실제 설치 program/data를 해시로 고정하고 RV32 명령어와 host ABI를 대조했다. `airoha-npu-fdk` 및 ClankerNPU는 참고용 재구현/개발킷이며 vendor 원본 source가 아니다. AN7583/MT7993 등의 결과를 AN7581/MT7996 동작 증명으로 가져오지 않는다.

확인한 경계는 descriptor 대기, replacement buffer와 TX token의 서로 다른 수명, mailbox timeout 뒤 늦은 firmware 완료, STOP이 안전한 작업 취소가 아니라는 점이다. 임의 timeout 추가·token 재사용·NPU STOP/reset은 메모리/DMA 손상 위험을 해결하지 못한다. WM/WA/DSP 내부의 암호화된 PS/TX 소비자 구현 전체는 검증 범위 밖이다.

r43의 정확한 조건:

```text
program SHA256: e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643
data SHA256:    61a75afb052feed2ceb2f3023e16f50317c05c78f9c8e564bf01924ce39c7ec1
program offset: 0x9e1a
bytes:          9374f50f -> e284e1c5
DRAM SHA256:    389cfecb074fc21c163006c791b65f9628fe790cfb682f2e288b71c14104a736
```

ring 여유가 7일 때 consumer 예산이 0이 될 수 있고, 기존 consumer가 첫 처리 뒤 unsigned 감소로 큰 값이 되는 경로를 확인했다. 다른 종료 조건도 있으므로 무한 루프라고 단정하지 않는다. 부팅 loader는 일치하는 쌍에만 기존 반환 경로를 사용하도록 수정하고 전체 readback 해시를 검사한 뒤 core를 시작한다. 원본 vendor 파일은 유지한다.

검사 범위는 최종 prepared source 14그룹, 추출 loader의 원본 1건/후보 24건, 제한 RV32 실행의 양수 131,082건 및 0 입력 2건이다. 전체 firmware 실행·동시성·DMA를 에뮬레이션한 것이 아니다. 설치 검증은 30 PASS / 0 FAIL / 0 SKIP, 설정 34개·모듈 74개 비교와 NPU version 응답·실제 가속 flow 확인을 포함했다. 빌드 경고 408회/서로 다른 문구 154개는 검사 통과와 별도로 남겼다.

**기존 카운터로 가드 hit를 셀 수 없다.** 동일 epilogue, 반환값 미사용, 같은 consumer index 재저장 때문에 다른 경로와 구분되지 않는다. cached DMA index를 사용하는 호출 순간의 free 값은 순차 host snapshot으로 복원되지 않는다. 미사용처럼 보이는 SRAM에 카운터를 쓰거나 관측을 위해 halt/reset하지 않는다. [설계](npu-budget-guard-20260926/GUARD_DESIGN.md), [동시성](npu-budget-guard-20260926/CONCURRENCY_REVIEW.md), [관측 한계](mlo-r43/NPU_OBSERVABILITY.md)를 먼저 읽는다.

## 7. 아직 남은 코드·검증 항목

[9월 26일 전체 검토](mlo-r33/FULL_REVIEW_20260926.md)는 수정 전 상태를 포함한다. F02/F03/N01/F09/F10은 r34에서 보완했고 F04는 앞선 bridge package에서 핵심 경로를 수정했다. 현재 남은 항목을 옛 표의 건수 그대로 옮기면 안 된다.

| 항목 | 남은 문제 / 확인할 것 |
|---|---|
| F01 | Wi-Fi 읽기 전용 위임 계정의 실행 권한 범위. 그런 계정이 실제 사용된 증거와 별개로 ACL 경계 검토 필요 |
| F05 | UCI set/commit 실패를 삼킨 뒤 Wi-Fi를 재시작하는 UI 경로 |
| F06 | 비활성 MLO 프로필 저장에도 활성 radio 2개를 강제하는 조건 |
| F07 | 편집 profile과 표시 profile 선택 불일치 |
| F08 | UCI 이름으로 netdev를 추정하여 custom ifname/복수 profile을 오인할 가능성 |
| 가속 수명 | primary 변경 뒤 기존 PPE binding 갱신, RRO/PPE 삭제 오류·실패 복구의 완결성 |
| upstream 후보 | RX31 IRQ, GRO/ring/DMA mask, 995/996의 자체 KEEP_TTL/FDB/slot 수정과 병합 |
| 진단 부하 | 상세 trace OFF에서도 남는 일부 카운터 비용. 과거 CPU 상한의 원인으로 단정할 수 없음 |
| 전체 기능 | WAN/IPv6/UDP/VLAN/QoS/Tailscale, clean Linux build, 3-link MLO, 장기 안정성·Air upload 등 완전 검증 안 됨 |

RX31 index가 고정됐다는 이유만으로 stall이라고 결론내린 적은 정정했다. r32의 128 descriptor sample은 DONE/meta=0이었고 고속 전송도 있었다. IRQ·DONE·metadata·실제 traffic을 같은 시각에 맞춰야 한다. TXFREE overrun guard도 잘못된 report의 생산 원인을 고친 것으로 설명하지 않는다.

## 8. upstream 및 포럼 조사 상태

자료 조회 날짜는 9월 25–28일이다. **10월 3일 upstream 최신 전체 검토를 새로 한 것은 아니다.** 이어받는 시점에 remote를 다시 확인해야 한다.

- 9월 26일 일반 UBI2 source `54e453b074...`, kernel 6.18.52를 내려받아 비교했다. 9월 24일과 공통 firmware 12/12가 같았고, 새 Airoha 995/996은 L2 TTL 및 cross-ingress guard였다. 자체 IPv4 HNAPT KEEP_TTL을 대체하지 않는다.
- RX31/GRO/ring/DMA 후보 및 mt76 공개 PR은 별도 검토 대상이다. 커널 숫자만 올리면 mac80211 backports까지 자동 갱신되는 것이 아니다.
- libpcap 1.10.7 / tcpdump 4.99.7 recipe 업데이트를 검토했으나 미반영이다. 현재 임시 캡처 도구는 firmware 내장과 별개다. [범위와 검증 조건](mlo-r42/endpoint-clock/PATCH_CANDIDATES.md).
- 사용자가 지정한 [2c12af9](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/2c12af94ce461d6037e5c16ac257f70943b9a417)는 loopback GSO 및 TCP 기본 send buffer 상한 변경이다. 공유기가 TCP endpoint가 아닌 LAN→Wi-Fi bridge 시험의 직접 수정으로 볼 수 없다. 적용하지 않았다. [검토 원문](upstream-20260928/2c12af9-review.md).
- FDK/ClankerNPU errata는 사용 바이너리의 SHA/주소/명령어가 일치하는지 확인해야 한다. 새 프로젝트의 주장을 현재 vendor 결함으로 확정하지 않는다.
- 포럼 일부는 HTTP 403으로 최신 본문 확보에 실패했다. “새 정보 없음”으로 판정한 것이 아니다. [전체 검토의 포럼·소스 링크](mlo-r33/FULL_REVIEW_20260926.md)를 재사용한다.

## 9. 로컬 파일·빌드 환경

작업 폴더를 `$WORKSPACE`라고 쓴다. 공개 문서에는 개인 계정 경로와 주소를 넣지 않는다. 사용자에게 전달하는 별도 로컬 경로표에서 실제 위치를 확인한다.

| 경로 | 역할 |
|---|---|
| `$WORKSPACE/publish-mlo-r29` | 최신 공개 source 및 현재 수정 기준 |
| `$WORKSPACE/OpenW1700k` | 이전 개발 checkout. 최신 r43 대신 그대로 빌드하지 않는다 |
| `$WORKSPACE/builds` | 별도 배포/CI checkout. 이전 미공개 변경은 이번에 source snapshot으로 보존 |
| `$WORKSPACE/build-volume/source` | 실제 prepared build tree가 올라오는 마운트 지점 |
| `$WORKSPACE/w1700k-build.sparsebundle` | case-sensitive build disk 기반 |
| `$WORKSPACE/artifacts/mlo-repair-2026-09-08/build.shadow` | 위 disk의 쓰기 변경. sparsebundle만으로 최신 build가 복원되지 않음 |
| `$WORKSPACE/artifacts/` | 버전별 검증, local scripts, private 증거·백업 |
| `$WORKSPACE/source-cache/` | 조사용 upstream/FDK source |

**10월 3일 확인:** `build-volume`은 비어 있고 `build-volume/source`가 없으며 관련 mount도 없다. sparsebundle과 약 81.60GB logical-size shadow 파일은 존재한다. 이는 빌드 볼륨이 현재 마운트되지 않은 상태이며 파일 유실 판정이 아니다. 재개할 때 기존 shadow를 사용한 마운트부터 확인하고 새 빈 source를 덮어쓰지 않는다. iCloud 전환 당시 절대경로/ccache/TMPDIR 문제는 정리했으며 `artifacts/mlo-repair-2026-09-12/FILE_INTEGRITY.json`이 당시 검증이다.

9월 27일 확인된 불필요 파일 90개, 할당량 293.23GB를 정리했다. 주원인은 바깥 checkpoint 저장소의 중단된 `tmp_pack_*` 83개였고 정식 source repo의 pack을 임의 삭제한 것이 아니다. 중복 이미지도 보존본 hash 확인 뒤 제거했다. 10월 3일 바깥 `.git/objects/pack`은 0B, 호스트 여유는 약 124GiB였다. 당시 303.92GB였던 여유와 혼동하지 않는다. 새 삭제는 하지 않았다.

### 다음 빌드 절차

1. 현재 source, image hash, module ABI, 공유기 build ID, 실제 mount를 재확인한다.
2. [r29 build 기반](mlo-r29/BUILD.md), [r34 feed/overlay 통합](mlo-r34/BUILD.md), [r43 config](mlo-r43/r43.config), [현재 manifest](mlo-r43/build-manifest.json)를 함께 쓴다. 이전 r34 config를 그대로 쓰지 않는다.
3. feed pins: packages `d50c9e2ac63808f8ea487ef8bc91632e7a483804`, LuCI `289a7260434d4b8212a9cc6cf6160cb1935270c1`, routing `4b9891b9136259f93294a424507ed24c5e8c1cbd`.
4. Darwin arm64 GNU make 4.4.1, GNU getopt, TFA `-include stdint.h`, libpfring target AR, ovpn module version, LuCI feed patch의 기존 조건을 보존한다.
5. 새 버전 artifact 폴더에 기록한다. 9개 make 단계를 실제 실행하고 make dependency 판단을 사용한다. 과거 JSON에 성공이라고 적혔다는 이유로 빌드를 건너뛰지 않는다.
6. fresh patch preparation, prepared source hash, host 회귀, FIT/board/UBI, kernel/module 74개 ABI/hash, firmware 11개, wpad/LuCI 338파일 및 package manifest를 변경 범위에 맞춰 검사한다. 기존 결과 숫자를 새 버전 통과로 재사용하지 않는다.
7. 설치 전 백업·복구와 유선 관리 경로를 확인한다. 설치 뒤 guard log만 보지 말고 NPU version 응답·실제 가속 flow·유선·설정 보존을 확인한다. 이미지를 섞거나 NPU를 runtime rebind하지 않는다.
8. 기존 tag/image를 덮어쓰지 않고 새 r prerelease를 공개한다. source push, tag, body, asset bytes/SHA를 원격에서 검증한다.

## 10. 재개 순서와 완료 기준

1. 이 문서와 r43 결과를 읽고, Git 브랜치·마운트·장치 build·Mac 유선 route·server 상태를 읽기 전용으로 갱신한다. 오래된 IP, interface 번호, SSH socket, 로그인 세션을 그대로 믿지 않는다.
2. 소스만으로 재현 가능한 F01/F05–F08 등을 작은 단위로 검토하거나, 기존 MLO 미해결 증거를 우선 좁힌다. 단말/환경이 필요한 작업을 무한 반복하지 않는다.
3. MLO 양단 시험은 로컬 `artifacts/npu-zero-budget-r43-2026-09-27/endpoint-pair/` 도구를 먼저 검토한다. `README.md`, `PREPARATION_RESULT.json`, `run.py`, `mac-capture.sh`, `check-pair.py`, `check-capture.py`가 있다. 공개 snapshot은 [endpoint-pair](mlo-r43/endpoint-pair/README.md)다. 10월 3일 `check-pair --self-test`와 `run --self-test`는 PASS였지만 `check-capture.py` 첫 deadline 사례는 `/bin/ps` 제한 없이도 `status=FAILED, reason=deadline, tcpdump_exit=0`으로 실패했다. 이후 사례는 미실행이다. 2 PASS / 1 FAIL을 그대로 인계하며, 과거 12 PASS를 현재 준비 완료로 재사용하지 않는다. 원본 스크립트를 고치거나 이 실패 조건을 우회한 상태가 아니다.
4. Mac 일반 en0 캡처는 sudo가 필요하다. monitor mode는 기존 시험에서 0 packets였으며 주 경로로 쓰지 않는다. 새 캡처 readiness를 확인하고 제한된 시간 안에 서버·clock marker·60초 4-stream 시험을 시작한다. 기존 세션/marker를 지우며 성공으로 꾸미지 말고 별도 세대로 보존한다.
5. 이전 pair 준비는 캡처 age guard 또는 인증/시작 시간 문제로 중단됐다. 빈 캡처는 본시험이 아니며 실제 pair 비교 완료 자료가 없다. `received by filter`와 saved records가 같아야 한다는 조건도 Darwin에 적용하지 않는다. kernel drop 0과 저장·회전·전체 시간 범위를 각각 확인한다.
6. 같은 TCP sequence byte range를 양단에서 비교한다. GSO/LRO 때문에 packet 수를 1:1로 맞추지 않는다. clock bounds를 전후에 측정하고, data 도착·ACK 출발·서버 ACK 도착 순서로 구분한다. Mac TX capture만으로 RF 송신 성공을 증명할 수는 없다.
7. 저하 회차와 정상 회차를 같은 조건에서 분리하고 원인에 대응하는 최소 변경을 검증한다. CPU·PS·PPE/NPU queue는 보조 증거이며 상관관계만으로 firmware 원인이라고 결론내리지 않는다.
8. 완료는 원래 실패 조건의 재현과 원인 증거, 수정 후 반복 비교·재연결·절전 복귀 검증, 유선/가속 정확성 유지까지 포함한다. 정상 Mac 한 회차·정적 test·빌드 성공은 완료 조건을 대신하지 않는다.

## 11. Claude에 전달할 시작 지시문

> 이 저장소의 docs/CLAUDE_HANDOFF_20261003.md와 AGENTS.md를 먼저 읽고 작업을 이어가라. 최신 작업 브랜치는 codex/mlo-r30-bridge-offload이고 공개 remote는 fork=VultaV/OpenW1700k다. CPU/브리지 가속 병목은 개선했지만 Air의 MLO 간헐 멈춤 원인은 미해결이다. r43은 실험용 NPU DRAM guard이며 효과가 입증됐다고 가정하지 마라. 기존 코드·검증·private 증거를 보존하고, 현재 빌드 볼륨 마운트와 장치 상태부터 다시 확인하라. 반복 Air 수동 시험보다 Mac 무선 시험을 사용하되 Mac 정상 결과로 Air 해결을 선언하지 마라. 유선 관리 연결을 보호하고, r 버전마다 source·빌드·개선 사항을 GitHub prerelease로 공개·검증하라. Matter는 해결됐으니 재조사하지 마라. 이미 실패하거나 철회한 실험을 근거 없이 반복하지 말고, 기존 양단 캡처 준비와 미해결 코드 항목에서 다음 작업을 선택하라.

## 12. 이번 공개 정리 범위

- 기존 r43 source·펌웨어·19개 release asset은 업로드되어 있음을 10월 3일 원격 조회로 확인했다. 기존 tag와 firmware를 교체하지 않는다.
- 이 인계서, 최신 문서로 연결하는 README, [9월 28일 upstream 검토](upstream-20260928/2c12af9-review.md), [초기 builds 미공개 CI/updater 변경과 회귀 시험](builds-local-20260908/README.md), [양단 캡처 도구 검토용 소스](mlo-r43/endpoint-pair/README.md)를 추가한다.
- 초기 `OpenW1700k/` dirty 변경은 현재 source에 반영됐거나 오래된 버전임을 대조했다. 예전 mt76 release 14를 최신 release 32 위에 덮어쓰지 않는다. `builds/`의 역사적 diff도 r43에 적용하는 patch가 아니라 기준 commit에 대한 보존본이다.
- 초기 builds 시험은 workflow 53, custom 4, updater 20, UI 5개 PASS였다. updater가 내부 호출한 UI 5개는 중복 합산하지 않는다. GitHub Actions 실제 실행 성공을 의미하지 않는다.
- raw packet, 설정/복구 백업, 인증 자료, build cache/disk는 로컬에 보존한다. 공개용 캡처 소스는 사용자 경로·LAN 주소를 제거한 `.txt`이며 그대로 실행할 수 없다. Matter 관련 새 자료는 사용자 요청에 따라 제외했다.
