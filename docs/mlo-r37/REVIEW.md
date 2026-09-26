# r37 mailbox 후속 검토 — 2026-09-26

## 수정 대상

r36의 `__airoha_npu_send_msg()`는 모든 WLAN/PPE 명령을 core 0의 lock으로 직렬화하고 최대 500ms 동안 응답을 기다린다. coherent buffer는 timeout 뒤에도 살아 있지만, 다음 호출은 완료 여부를 확인하지 않고 같은 buffer와 주소·길이·sequence·CTRL3를 덮어쓴다. 이때 이전 응답이 도착하면 새 요청의 응답으로 읽힐 수 있다. buffer 수명 보존만으로 요청 소유권이 보존되지는 않는다.

r37은 기존 register 상태를 재사용한다. lock 아래 CTRL3를 먼저 읽고 `WAIT_RSP=1 && DONE=0`일 때 `-EBUSY`를 반환한다. 읽기 실패도 그대로 반환한다. 이 두 거절 경로는 요청 buffer, CTRL0–3와 reply를 변경하지 않는다. 초기 CTRL3=0이나 DONE이 올라온 기존 성공/실패 응답은 새 요청을 허용한다. 상태 조회 직후 이전 요청이 완료돼도 이번 호출만 거절되며 다음 호출이 진행할 수 있다. 추가 대기 루프·software pending flag·공개 구조체 변경은 없다.

현재 driver는 모든 요청에 WAIT_RSP를 설정한다. 실제 vendor program의 선택 함수 81개 명령을 원본 byte 및 새 Capstone 해석으로 대조했다. `0x84003d36`의 WAIT 분기는 조기 DONE 쓰기를 건너뛰며, callback `0x84003d7e`가 반환한 뒤 `0x84003d98/3da0`에서 DONE을 게시한다. 그 뒤 함수 epilogue에는 payload 접근이 없다. [범위·해시·8개 anchor](MAILBOX_FIRMWARE.json)를 보존했다. FDK의 재구현을 vendor binary의 증명으로 대체하지 않았다.

DMA coherent 메모리는 CPU와 장치가 함께 접근하므로 소유권 규칙이 별도로 필요하다. 관련 플랫폼 계약은 [Linux DMA 문서](https://docs.kernel.org/core-api/dma-api-howto.html)를 참고했다. 이번 수정의 타이밍·동작 근거는 위 실제 host 및 vendor 경로에 한정한다.

남는 조건: 영구 미완료 요청은 계속 busy이며 timeout 자체가 취소되지는 않는다. 부팅 이전 stale WAIT, 동시 firmware reset, 외부 no-WAIT 요청을 복구하는 규칙은 추가하지 않았다. 상위 caller가 실패를 무시하는 기존 문제도 그대로다. DONE은 mailbox handler 완료이며 Wi-Fi DMA 전체의 정지 증명이 아니다. 새 runtime·무선 시험이나 Air 원인 귀속은 없다.

## 추가로 확인한 남은 결함

아래 위치는 r36 prepared `mt76-2026.09.01~01367e60`, `linux-6.18.44` 기준이다. 이 항목을 r37에서 해결했다고 표시하지 않는다.

| 항목 | 실제 경로·위험 | 안전한 수정에 필요한 경계 |
|---|---|---|
| NPU 공유 IRQ 수명 | mt76 `npu.c:307`은 devm shared IRQ에 `q`를 등록하고 handler `:199`는 RCU 전에 `q->dev`를 읽는다. remove/probe 실패에서 NAPI·queue·device는 해제되지만 IRQ devres는 callback 반환 뒤 해제돼 중간 IRQ의 오래된 `q` 접근 창이 남는다. | 등록 성공 여부를 추적하여 NAPI·queue·device 파괴 전에 명시적으로 IRQ를 해제·동기화해야 한다. source mask만으로 다른 공유 IRQ의 진입을 막지 못한다. firmware DMA quiescence는 별개다. |
| NPU 중지·재시작 실패 무시 | `mt7996/mac.c:2672`가 stop 반환을 버리고 `:2709` DMA reset, `:2711` token 반환을 수행한다. `:2744` 재초기화 오류도 버리고 reset 해제·queue wake·완료 로그로 진행한다. | 단순 return 또는 full reset도 안전한 대안으로 증명되지 않았다. full reset 역시 NPU 중지 없이 token을 반환하므로 DMA 소유권·정지 보장이 먼저 필요하다. |
| PPE SRAM flush 오류 누락 | kernel `airoha_ppe.c:1448`의 내부 `int err`가 외부 `err=0`을 가려 commit 실패 후에도 성공을 반환한다. | 기존 상위 init 오류·QDMA 정리 경로를 함께 검증한 별도 수정 대상이다. |
| RRO 초기화·삭제 오류 | `mt7996/init.c:1032,1097`의 주소 등록, `:1188` NPU 삭제, `:1214` WM reset 결과가 무시된다. | 부분 등록, 늦은 완료, 세션 재사용 순서를 모른 채 무조건 retry하면 안 된다. MCU timeout recovery work는 이미 존재한다. |

공통 NPU deinit의 RCU grace 부족도 검토했다. 다만 NPU/PPE get이 managed device link를 만들고 supplier 제거가 consumer callback을 기다리므로, put 즉시 supplier가 해제되어 다음 queue cleanup이 UAF라는 주장은 확정하지 못했다. RCU 수명 보완과 shared IRQ의 `q` 수명 문제를 구분한다.

IRQ 수명 수정은 정상 remove의 공통 DMA cleanup과 probe 실패의 `mt76_free_device()` 직행 경로를 모두 처리해야 한다. NAPI가 이미 비활성화된 뒤 `napi_disable()`을 중복 호출하면 안 된다. poll은 `napi_complete_done()` 이후에도 IRQ를 다시 켤 수 있으므로 callback 종료까지 확인하고 등록을 제거해야 한다. 등록 성공 상태의 추적·NAPI 정리 소유권을 검토했으나, r37에 이 후속 설계를 구현하거나 검증한 것으로 표시하지 않는다.

## 전체 검토 항목의 현재 상태

[r33 전체 검토](../mlo-r33/FULL_REVIEW_20260926.md)의 번호를 유지하되 당시 미해결 개수를 현재 개수로 인용하지 않는다.

- r34에서 소스로 수정한 항목: F02/F03 링크 선택자·WCID 예약 반환, F09/F10 업데이트 UI 재현성과 빈 결과 처리, N01 watchdog 작업 수명, N02 빌드 단계 생략. F04 브리지 규칙 갱신도 기존 수정 범위에서 유지한다.
- 남은 설정·권한 문제: F01 읽기 전용 위임 계정의 변경 명령 권한, F05 UCI 실패를 무시한 재시작, F06 비활성 MLO 프로필 저장 거절, F07 프로필 선택 불일치, F08 실제 netdev 추정 오류.
- 남은 driver 경계: 실패한 링크 activation의 rollback, 이미 게시된 PPE binding 무효화, SRAM 삭제 실패 뒤 객체 정리, 위 IRQ·stop/reset·RRO 오류 처리. 새 mailbox 보호가 이들을 해결하지는 않는다.
- vendor NPU의 zero-budget 후보 분석은 [별도 기록](../npu-budget-guard-20260926/README.md)에 있으며 바이너리에는 적용하지 않았다. WM/WA/DSP 내부 PS/TX 구현 전체도 직접 검증 범위 밖이다.
- WAN·IPv6·UDP·VLAN·QoS·Tailscale 전체 기능, 모든 패키지 CVE 및 장기 누수 검사는 완료된 것으로 표시하지 않는다. 추가 무선 시험 없이 확인한 소스 결함과 이미지 검증을 기록한 검토다.

## 빌드 경고 분류

전체 시도 로그에서 1,123회·고유 307개 메시지를 수집했다. r36의 고유 148개는 모두 다시 관측됐고 159개 메시지가 추가로 관측됐다. 증분 빌드의 재컴파일 범위가 달라 새 관측을 새 결함이나 이번 패치의 회귀로 세지 않는다. 상세 위치와 탐지 규칙은 [BUILD_WARNINGS.json](BUILD_WARNINGS.json)에 남겼다.

새로운 use-after-free 경고 1건(`proto.c:60`), 초기화 경고 3건(`mib.c:96/182`, `io.c:650`), pointer 폭 경고 2건(`ttcp.c:372`, `atmloop.c:119`)은 모두 linux-atm 2.5.2에서 발생했다. 이 패키지와 해당 실행 파일은 추출한 r37 이미지에 없었다. `free(call)` 뒤 `%p` 출력과 초기화하지 않은 주소를 `connect()`에 전달하는 코드 등은 그 소스의 검토 대상으로 남지만, 설치 이미지의 NPU 결함으로 귀속하지 않는다.

누락 의존성 14개 메시지에 해당하는 활성·설치 recipe family는 0개, 빈 kmod 28종 중 이미지 설치 항목은 0개였다. 수정 파일 `airoha_npu.c`를 직접 가리키는 경고는 없었다. 이 분류는 나머지 경고가 무해하다는 판정이나 전체 패키지 보안 감사가 아니다.

릴리스 후 경고 대조에서 **설치된 `ip-bridge`의 확장 netlink 오류 진단 제한**도 확인했다. iproute2 tctiny variant의 `lib/libnetlink.c:152–157`은 libmnl 없이 `nl_dump_ext_ack()`를 0 반환 stub으로 빌드한다. 따라서 상세 오류 설명이 빠질 수 있으나 forwarding 실패를 뜻하지는 않는다. stripped package와 r37·r36의 `/usr/sbin/bridge` SHA256은 모두 `ab7cf214c20a942fe346fee83cc1de12cc3618e003d2fd10d2a23e6166f64ce8`로 동일하다. 새 바이너리 회귀가 아니라 기존 진단 기능 제한으로 기록한다. PPTP packed-member 경고는 이미지에 없는 `ppp-mod-pptp`에 해당하며, 설치된 기본 PPP와 구분한다. 이 후속 문서는 r37 태그·이미지·첨부 파일을 변경하지 않는다.

## 최신 공식 패치 재조회

2026-09-26 재조회에서 r33의 앞선 검토 이후 새로 적용할 stop/reset·RRO teardown·MCU timeout 수정은 확인하지 못했다.

- [공식 mt76 HEAD be5ce791](https://github.com/openwrt/mt76/commit/be5ce7910521492d4a2e4ce7ee3843680a46c047)은 9월 1일 그대로였다. 열린 PR 34개, 당일 갱신 0개였고 NPU 검색은 기존 [#1069](https://github.com/openwrt/mt76/pull/1069), RRO 검색은 0개였다. 검색 결과가 모든 미병합 변경의 부재를 증명하지는 않는다.
- [Linux NPU watchdog 4bdee806](https://github.com/torvalds/linux/commit/4bdee8060d1e4581624e68fbd369b1afb14df4bc)은 해당 파일의 최신 변경이며 이미 r36에 백포트돼 있다.
- [NPU stop e992ff88](https://github.com/openwrt/mt76/commit/e992ff8842b33acbfd41aa65cf6ead1fd4d634cb), [RRO 삭제 이벤트 12-byte 수정 bd49f063](https://github.com/openwrt/mt76/commit/bd49f06353d7e8cdfa1458912ba9a866870cb795)도 현재 tree에 포함된다. 새 미반영 패치로 세지 않는다.
- [OpenWrt #25348](https://github.com/openwrt/openwrt/pull/25348)은 6.12용 DT binding·`request_firmware_direct()` 백포트다. r36의 direct firmware 로딩을 대체하는 stop/mailbox 복구 수정이 아니다.
- [DMA 방향 수정 6f884eb8](https://github.com/torvalds/linux/commit/6f884eb87a79e0c482baef2ad96c96b81d024235)은 7월의 streaming DMA 수정이다. 현재 coherent bounce buffer와 구분한다.

lore·netdev/net-next 및 일부 공식 Gitiles 원문 조회는 실패했다. 따라서 새 메일 패치 전체나 포럼에 새 정보가 없다고 결론 내리지 않는다. 기존 일반 UBI2·포럼 조사와 UI/ACL 문제 목록은 [전체 검토](../mlo-r33/FULL_REVIEW_20260926.md), 현재까지 반영한 driver 수정 경계는 [r35 검토](../mlo-r35/REVIEW.md)와 [r36 검토](../mlo-r36/REVIEW.md)를 함께 참고한다.
