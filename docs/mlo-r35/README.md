# r35: MLO 링크 전환·가속 경로 조회

[한국어 릴리스 기록](../releases/mlo-r35-20260926.md)에 변경 이유와 실제 검증 결과를 보존했습니다. [REVIEW.md](REVIEW.md)는 전체 검토의 남은 항목과 새 공개 패치 판단을 이어갑니다.

- 성공한 MLO 링크 변경 뒤 공유 TXQ 재등록.
- 동일 primary로 BSS/WCID 조회, RCU 문맥에 맞는 VIF 조회, 비활성 MLO 경로 거부.
- vendor NPU 바이트 대조와 RRO 경계 기록. 펌웨어 바이너리 변경 없음.

`BUILD_RESULT.json`, `BUILD_WARNINGS.json`, `build-manifest.json`, `SHA256SUMS`가 이미지별 증거입니다. [BUILD.md](BUILD.md)의 pinned input 절차를 사용합니다. **장비 설치·부팅·무선 시험은 하지 않았고 Air 간헐 멈춤 해결은 입증되지 않았습니다.**
