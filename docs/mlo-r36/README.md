# MLO r36 진행 현황

호스트 NPU TXWI·주소를 DONE 공개 전에 정렬하는 최소 수정입니다. 전체 빌드·이미지 검증을 마쳤으며 변경 모듈은 `mt76.ko` 하나입니다. **장비 설치·부팅·추가 무선 시험은 하지 않았고 Air 간헐 멈춤 해결은 미확정입니다.**

- [한국어 릴리스 노트](../releases/mlo-r36-20260926.md)
- [전체 후속 검토와 미해결 범위](REVIEW.md)
- [실제 NPU TX 예산 경계와 stop/timeout](NPU_TX_BUDGET.md)
- [교체 버퍼·TX token 풀과 reset 경로](NPU_COMPLETION_POOLS.md)
- [기존 Air 기록의 시각·계측 범위 재검토](AIR_EVIDENCE.md)
- [빌드·재실행 방법](BUILD.md), [결과와 해시](BUILD_RESULT.json), [경고 집계](BUILD_WARNINGS.json)

기존 최신 빌드·공개 패치·포럼 조사와 나머지 UI/권한 목록은 [9월26일 전체 검토](../mlo-r33/FULL_REVIEW_20260926.md), r34/r35 수정 상태는 [이전 검토](../mlo-r35/REVIEW.md)를 참고하십시오. 이번 릴리스에 NPU binary patch나 새 펌웨어 blob은 포함하지 않았습니다.
