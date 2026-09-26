# r39 — NPU TX 집계 세션 갱신

계속된 NPU TXS에도 BA 세션이 유휴로 종료될 수 있던 갱신 누락을 수정했다. **장비에 설치하지 않았고 추가 무선 시험을 하지 않았으며 Air 멈춤 해결은 미확정이다.**

- [한국어 릴리스 노트](../releases/mlo-r39-20260926.md)
- [호출 경로·원본 실패·Air 기록·펌웨어 후속 검토](REVIEW.md)
- [빌드 재현](BUILD.md), [최종 결과](BUILD_RESULT.json), [경고](BUILD_WARNINGS.json)
- [BA 회귀 검사 기록](ba-regression-tests.json), [기존 Air TXS 근거](AIR_TXS_EVIDENCE.json)

변경 모듈은 `mt7996e.ko` 하나다. kernel·다른 73개 모듈·vendor firmware는 r38과 같다. 펌웨어 SHA256: `78b54197e6249eaf9d8bbaccb88047098fb64d2a7218d5d9a9d4a6d4d568c8e9`.

- [공개 후 최신 빌드·패치 재조회](UPSTREAM_FOLLOWUP.md): 같은 kernel73 태그의 파일 교체 확인, r39 태그·이미지 유지.

- [9월 27일 기존 Air BA 기록·kernel73 내부 비교](OFFLINE_EVIDENCE_20260927.md): r29 정상 세션의 timeout0 확인, r32 실패 원인은 미확정.
