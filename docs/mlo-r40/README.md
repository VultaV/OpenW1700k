# r40 — NPU 경로 RED 초기화 후보

2026-09-27. **빌드 9단계, 실제 소스 검사 13개 프로그램과 이미지 검증은 통과했다. 설치 후 검증 24건을 통과했고 Mac 시험 결과는 아래에 기록했다. Air 절전 복귀 멈춤 해결은 미확정이다.**

[0036 패치](../../package/kernel/mt76/patches/0036-mt7996-initialize-red-for-npu-offload.patch)는 MT7996에서 NPU가 활성화된 경우, MediaTek의 non-WED offload 지원을 근거로 WM RED 설정과 WA enable·토큰 예산 전송을 초기화에 추가한다. source 3 예산은 현재 host `token_size`를 사용한다. MT7996 이외 장치와 NPU가 꺼진 경로는 기존 WA 초기화를 따른다. NPU·WM·WA 펌웨어 바이너리 변경은 후보에 포함하지 않는다.

이는 공식 패치의 Airoha NPU 호환성이나 실제 개선 효과가 검증됐다는 뜻은 아니다. WM ACK는 확인할 수 있지만 WA 두 명령은 비동기 전송이며, 성공 반환은 RED 상태 readback이 아니다. NPU의 TXP source 필드가 0이라는 오프라인 분석도 펌웨어 RED 예산 배열과의 대응을 입증하지 않는다.

이전 r39 시험에서는 Mac Wi-Fi 설정 화면을 열었을 때 반복 저하가 관측됐지만, 이번 변경 전 새 기준 시험에서는 화면을 연 60초 동안 평균 1,957Mbps·최저 1,857Mbps로 반복 저하가 없었다. 닫은 시험은 평균 1,824Mbps·최저 96Mbps였고, 500Mbps 미만 두 표본은 시작 직후 2초에 집중됐다. 따라서 이 후보를 기존 현상의 확정 원인 수정으로 설명하지 않는다.

- [후보 범위·공식 근거·검증 한계](REVIEW.md)
- [r39 RED 계약 및 송신 TCP 분석](../mlo-r39/RED_CONTRACT_20260927.md)
- [r39 Mac 경로 비교](../mlo-r39/MAC_PATH_FOLLOWUP_20260927.md)
- [후보 빌드 manifest](build-manifest.json)

[설치·Mac 시험 결과](DEVICE_TESTS_20260927.md): 닫힘 5분 평균 1,969Mbps, 열림 반복 저하 지속. r40은 실험 상태를 유지한다.
