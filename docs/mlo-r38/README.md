# r38 — PPE SRAM 초기화 오류 전파

SRAM commit 오류 뒤 성공으로 초기화를 계속하던 변수 가림을 수정했다. 전체 빌드·이미지 검사와 PPE 16개 host 검사를 통과했다. **장비에 설치하지 않았고 추가 무선 시험을 하지 않았으며 Air 멈춤 해결은 미확정이다.**

- [한국어 릴리스 노트](../releases/mlo-r38-20260926.md)
- [수정과 NPU 복구·Air 증거 후속 검토](REVIEW.md)
- [빌드 재현](BUILD.md), [최종 결과](BUILD_RESULT.json), [경고](BUILD_WARNINGS.json)
- [원본·수정 PPE 검사](flush-regression-tests.json)

변경 모듈은 `airoha-eth.ko` 하나다. kernel·다른 73개 모듈·vendor firmware는 r37과 같다. 펌웨어 SHA256: `f946ebcb46c17b420da6333f4a482916083f3ec5e7180b383e64953bc67e7e96`.
