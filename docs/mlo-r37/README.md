# MLO r37 — NPU mailbox 요청 소유권 보호

NPU 명령이 시간 초과된 뒤 아직 완료되지 않은 요청의 coherent buffer를 다음 명령이 덮어쓰는 경로를 수정했다. 같은 lock 아래 기존 WAIT/DONE을 먼저 확인해 미완료 요청은 `-EBUSY`, 읽기 실패는 해당 오류로 반환하며 payload와 요청 레지스터를 보존한다. 늦은 응답이 완료되면 다음 호출은 정상 진행한다.

전체 빌드와 이미지 검증 완료. **새 무선 시험·공유기 접속·설치·재부팅은 하지 않았으며, Air 간헐 멈춤 해결은 미확정이다.** NPU program/data는 그대로이고 host module `airoha_npu.ko`만 변경됐다. kernel과 나머지 73개 모듈은 r36과 동일하다.

- [한국어 릴리스 노트](../releases/mlo-r37-20260926.md)
- [검토 근거·최신 상위 정보·남은 문제](REVIEW.md)
- [실제 vendor mailbox 명령 대조](MAILBOX_FIRMWARE.json), [145건 host 검사 결과](mailbox-tests.json)
- [빌드 재현](BUILD.md), [최종 결과](BUILD_RESULT.json), [경고 기록](BUILD_WARNINGS.json)

펌웨어 SHA256: `25df914fc11b4e09bce54d48c4370feca03b016da237f8fbd4f52eb081adec91`
