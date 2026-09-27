# r41 — 링크 활성화 실패 후 송신 큐 복구

2026-09-27. **9단계 빌드·13개 소스 검사·이미지 검증 완료. r41 설치·부팅 검증 24개도 통과했으며, Mac 무선 비교 시험도 완료했다. 초반 저하는 남아 있다.**

mac80211은 새 링크를 활성화할 때 `valid_links`를 먼저 바꾼 뒤 드라이버를 호출한다. 이 임시 마스크 때문에 mt7996의 공유 TXQ가 절전 검사에 걸려 스케줄 목록에서 빠질 수 있다. 링크 추가가 실패하면 기존 마스크는 돌아오지만, 이미 빠진 큐는 다음 enqueue까지 멈춰 있을 수 있다. 기존 r35의 성공 경로 재등록만으로는 이 실패 경계를 복구하지 못한다.

[r41 패치](../../package/kernel/mac80211/patches/subsys/9999-rearm-station-txqs-after-link-activation-rollback.patch)는 **실패한 활성화의 마스크 복원과 링크 정리 뒤**, 데이터가 남은 station TXQ를 공통 `schedule_and_wake_txq()`로 다시 등록한다. 기존 오류를 그대로 반환하며, 이후 송신은 기존 PS·AQL 검사를 따른다. 재설정 중에는 기존 wrapper가 큐를 DIRTY로 표시하고 드라이버 wake를 보류한다.

[회귀 검사](../../tests/test_mt7996_link_transition.py)는 실제 core 활성화·링크 제거·active-mask wrapper·schedule/wake 함수와 기존 mt76 scheduler/completion을 추출한다. 원본과 후보 각각 **39개 assertion, 예상 밖 실패 0개**다. 기존 24개 검사를 유지하고 core 경로 15개를 추가했다. 원본은 마스크 복원과 AQL 반환 후 backlog 10개가 미등록 상태로 남는 음성 대조를 정확히 재현했고, 후보는 같은 backlog 10개를 처리했다. 성공·early exit·빈 큐·fragment 큐·재설정 경로 및 반환값·링크·PS 상태 보존도 확인했다. ASan·UBSan 검사를 통과했다.

활성 목록, 잠금, hash/debugfs, 할당과 RCU는 host fixture다. RCU 해제 예약 뒤 callback을 즉시 실행하므로 실제 grace period·커널 동시 실행·DMA 수명은 검증하지 않는다. **최근 Mac 새 연결 초반 저하나 원래 Air 멈춤의 원인을 이 실패 경로로 확인한 것은 아니다.**

공식 Linux [`fd179f8a05be`](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/net/mac80211/sta_info.c)의 활성화 함수가 로컬 원본과 동일함을 비교했다. 특정 revision의 해당 함수 비교이며, 모든 상위 대기 패치를 조사했다는 뜻은 아니다.

- 이미지 검증: mac80211 package release **2 → 3**, `mac80211.ko`만 변경됐고 나머지 73개 모듈은 r40과 같다.
- kernel release는 `6.18.44-w1700k-mlo-r32`를 유지한다. 커널 payload·11개 펌웨어·338개 wpad/LuCI 파일이 r40과 같다.
- 설치·부팅: 설정 34개와 Tailscale 상태 보존, 모듈 74개 해시·AP·LAN 복구를 확인했다. Mac 무선 시험 결과는 후속 기록에 별도로 남긴다.

[릴리즈 기록 초안](../releases/mlo-r41-20260927.md) · [r40 새 연결 비교와 한계](../mlo-r40/FRESH_START_20260927.md)

[빌드 결과](BUILD_RESULT.json) · [경고 목록](BUILD_WARNINGS.json) · [SHA256](SHA256SUMS) · [실제 소스 대조](prepared-source-provenance.json)

빌드 경고는 383회·147종으로 r40과 같은 정규화 문구다. 회귀 PASS와 경고를 분리하며, 새 문구 0개가 기존 경고의 무해함을 뜻하지 않는다. 13개 소스 검사 및 설치 이미지 UI 9개 검사를 통과했다.

[설치·Mac 시험 결과](DEVICE_TESTS_20260927.md): 안정 후 평균 1.92Gbps, 0Mbps 없음. 새 연결의 첫 5초 저하는 유지되므로 원래 목표는 미완료다.

후속 진단: [동일 설정 전송률의 가속 경로 비교](scan-path-20260927/SCAN_PATH_COMPARISON_20260927.md) · [Neighbor Report 구성 후 비교](neighbor-report-20260927/NR_CONFIG_COMPARISON_20260927.md). NR은 설정·조회만 확인했으며 Mac의 요청·응답 수신·사용은 미검증이다. 빌드에서 DEBUG/MSGDUMP가 제외돼 런타임 로그 수준 변경으로 이 공백을 채우지 못했다. 설정 후에도 연결 나이 약 22초의 저하와 기존 33회·97채널 요청 순서가 관측됐다. 신규 제품 소스·펌웨어 변경 없이 진단 기록만 추가했고, 원래 Air 문제는 미해결이다.
