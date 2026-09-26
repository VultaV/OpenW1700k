# 2026-09-26 23:49 KST 공개 자료 후속 확인

r39 소스·태그·펌웨어 공개 후 공식 GitHub API를 다시 조회했다. 이 후속 기록은 r39 태그와 릴리스 첨부를 바꾸지 않는다. 공유기 접속·설치·재부팅·추가 무선 시험은 하지 않았다.

## 최신 빌드와 패치

- [일반 UBI2](https://github.com/w1700k/builds/releases/tag/ubi2_2026.09.26_r36602-54e453b074)는 `54e453b074fc243c33f6b6cc36f6b4e8a176aa45`로 동일하다. 앞선 이미지 비교에서는 NPU와 MT7996를 포함한 firmware 12개가 9월 24일과 바이트 동일했다.
- [kernel73](https://github.com/w1700k/builds/releases/tag/kernel73_2026.09.26_r36605-710dd8fa84)은 **기존 같은 태그가 재게시되고 파일이 교체**됐다. source `710dd8fa844785627ac3dd0ddc2799473fa947b5`는 기존 기록과 같다. 새 source 패치로 세지 않는다.
- kernel73 release ID는 `397165454→397270790`, asset ID는 `590310852→590844200`, 게시 시각은 `18:00:09→23:46:27 KST`다. 크기는 모두 23,335,747바이트지만 API SHA256은 `13602070022d59ad4c3201de134cb9b7de109c595100b02030b8ebe44d8d2c2f`에서 `fbbb6e650c8a477dc8bc7797ed6b98af1d14875e67e0fd914b219f748b9b2fdd`로 바뀌었다. [메타데이터 대조](UPSTREAM_REPUBLICATION.json)를 보존했다. 이 교체 이미지는 다운로드·내부 비교·설치하지 않았으므로 차이의 원인이나 안정성은 미확인이다. 업로드 전체 완료 여부도 단정하지 않는다.
- [fastbuild](https://github.com/w1700k/fastbuild/commit/bb2e64fe333236fa72489743bb8c60a4d6f001cc)와 [공식 mt76](https://github.com/openwrt/mt76/commit/be5ce7910521492d4a2e4ce7ee3843680a46c047)의 HEAD는 그대로다. mt76 열린 PR 34개 중 9월 26일 갱신은 0개였다. 조회 범위에서 새 미반영 stop/reset·RRO·MCU timeout 수정은 확인하지 못했다.
- NPU watchdog `4bdee806...`은 이미 백포트했다. 공식 PPE 오류 전파 `d7d81b003013...`는 6월 수정의 누락분이며 r38의 최소 수정에 반영했다. 신규 공식 패치와 기존 누락 보완을 구분한다.

## 포럼과 남은 범위

[Discussion #34](https://github.com/w1700k/builds/discussions/34), [#25](https://github.com/w1700k/builds/discussions/25)의 마지막 갱신 시각은 기존 기록과 동일했다. OpenWrt 포럼 #473 본문은 이번에도 접근 실패했다. 포럼에 새 정보가 없다는 결론은 아니다.

현재 반영 상태는 [r38 전체 항목 추적](../mlo-r38/REVIEW.md#남은-범위)과 [r39 BA 갱신 검토](REVIEW.md)에 있다. NPU runtime 정지·재설정/IRQ/RRO 오류 처리, PPE runtime 삭제 실패, F01/F05–F08 권한·설정 문제는 남는다. Air 순간 정체 원인과 해결도 미확정이다. WAN·IPv6·UDP·VLAN·QoS·Tailscale 전체 기능 및 전체 패키지 CVE 감사까지 완료한 것으로 표시하지 않는다.
