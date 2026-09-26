# r39 — NPU TX 집계 세션 갱신

계속된 NPU TXS에도 BA 세션이 유휴로 종료될 수 있던 갱신 누락을 수정했다. **9월 27일 장비 설치·부팅과 Mac MLO 시험을 완료했다. Air 멈춤 해결은 미확정이다.**

- [한국어 릴리스 노트](../releases/mlo-r39-20260926.md)
- [호출 경로·원본 실패·Air 기록·펌웨어 후속 검토](REVIEW.md)
- [빌드 재현](BUILD.md), [최종 결과](BUILD_RESULT.json), [경고](BUILD_WARNINGS.json)
- [BA 회귀 검사 기록](ba-regression-tests.json), [기존 Air TXS 근거](AIR_TXS_EVIDENCE.json)

변경 모듈은 `mt7996e.ko` 하나다. kernel·다른 73개 모듈·vendor firmware는 r38과 같다. 펌웨어 SHA256: `78b54197e6249eaf9d8bbaccb88047098fb64d2a7218d5d9a9d4a6d4d568c8e9`.

- [공개 후 최신 빌드·패치 재조회](UPSTREAM_FOLLOWUP.md): 같은 kernel73 태그의 파일 교체 확인, r39 태그·이미지 유지.

- [9월 27일 기존 Air BA 기록·kernel73 내부 비교](OFFLINE_EVIDENCE_20260927.md): r29 정상 세션의 timeout0 확인, r32 실패 원인은 미확정.

- [9월 27일 설치·Mac 실기기 비교](DEVICE_TESTS_20260927.md), [검증 수치](DEVICE_VALIDATION_20260927.json): Wi-Fi 설정 화면을 나간 상태에서 5분 평균 1.95Gbps. 화면을 열면 반복 저하가 재현돼 측정 조건에 반영했다.

- [9월 27일 CPU 전달·PPE 가속·유휴 후속 비교](MAC_PATH_FOLLOWUP_20260927.md), [수치와 증거 해시](MAC_PATH_FOLLOWUP_20260927.json): 같은 연결에서 CPU 1.16Gbps / 가속 1.97Gbps. 설정 화면 열림의 급락은 두 경로에서 재현됐다. 공식 UBI2 재게시본의 드라이버·펌웨어 동일 여부도 확인했다.
