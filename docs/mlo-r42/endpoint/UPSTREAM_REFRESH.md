# 공식 소스 재확인 — 2026-09-27 13:03 KST

새 일반 UBI2 배포는 있지만, 이번 변경에서 MLO·PS·NPU 정체를 직접 고친 패치는 확인되지 않았다. 설치된 r42는 커널 **6.18.44**, mt76 `01367e60db433534ad0aa3d3b6c886de8cb7d44c`에 자체 수정이 포함된 별도 빌드다.

[새 배포 `ubi2_2026.09.27_r36617-2af23e846e`](https://github.com/w1700k/builds/releases/tag/ubi2_2026.09.27_r36617-2af23e846e)는 11:58:23 KST에 게시됐다. [원본 소스](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/2af23e846eb82d18a066f7242a9902c0bee85fbc)는 `2af23e846eb82d18a066f7242a9902c0bee85fbc`다. 이미지 22,180,671바이트의 GitHub 표시 SHA-256은 `024f5925392d59c73b5dccb6fea330540d105704a040cda034b143abe7192664`이며, 이번에는 다운로드하거나 설치하지 않았다.

이전 `54e453b074fc243c33f6b6cc36f6b4e8a176aa45`와 커밋 그래프가 갈라져 있어, 재배치된 커밋 수 대신 두 전체 트리의 파일 경로와 Git blob SHA를 직접 비교했다. 10,720→10,740개 파일 중 실제 변경은 39개다. **Airoha·generic 커널 패치, mt76, hostapd, firmware 레시피는 모두 동일하다.** 새 소스의 mt76와 hostapd 기준도 각각 `01367e60…`, `831364bf…`로 유지됐다.

실제 새 변경과 적용 상태는 다음과 같다.

- [libpcap 1.10.7 / `b36d01c6`](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/b36d01c69682adf3eaf00f9e9414e99a6d0a0d41): BPF 인터프리터·`pcap_offline_filter()`의 경계, 명령, 나눗셈 및 반복 처리 등 보안 수정. 진단 도구에 관련되지만 PS 정체나 netlink 캡처 길이 계약을 고쳤다는 근거는 없다. r42 소스는 1.10.6으로 **미적용**이다.
- [tcpdump 4.99.7 / `b6bb254a`](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/b6bb254a85fe375cf923bc9da3eeceefd1526889): 캡처 도구 갱신. r42 소스는 4.99.6으로 **미적용**이다.
- [mtd TRX 검증·누수 수정](https://github.com/openwrt/openwrt/pull/25284), elfutils 0.196, bmips 6.18 및 Mercusys 변경: 이번 새 트리에는 있으나 정상 W1700K 무선 송신·절전 경로의 수정 근거가 아니다.

[공식 mt76 HEAD `be5ce791…`](https://github.com/openwrt/mt76/commit/be5ce7910521492d4a2e4ce7ee3843680a46c047)(9월 1일), [fastbuild `bb2e64fe…`](https://github.com/w1700k/fastbuild/commit/bb2e64fe333236fa72489743bb8c60a4d6f001cc)(7월 2일)는 이전 확인과 같다. Linux Airoha 경로 최신 [NPU watchdog 해제 순서 수정 `4bdee806…`](https://github.com/torvalds/linux/commit/4bdee8060d1e4581624e68fbd369b1afb14df4bc)(9월 24일)도 그대로이며 **r34부터 r42에 포함**돼 있다.

기존 r41의 [공식 `sta_info.c` 비교 기준](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/net/mac80211/sta_info.c)은 특정 활성화 함수 비교다. 전체 미병합 패치나 펌웨어 무결함을 보증하는 자료가 아니다. 이번 조회는 공식 릴리스·지정 소스 범위에 한정했고 포럼 전체를 재조회하지 않았다. 이미지 내부 펌웨어 동일성이나 실기기 개선 효과도 새로 검증하지 않았다. 정확한 참조·수치는 [UPSTREAM_REFRESH.json](UPSTREAM_REFRESH.json)에 기록했다.
