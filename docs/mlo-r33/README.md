# MLO r33 패키징 검증

r32 이미지에 포함된 가속 패키지가 r30 커널만 허용하던 오류를 수정합니다. `bridge-flow-offload 1.0-r3`는 TTL 실측을 통과한 r30·r32 커널만 허용합니다. r33은 r32 커널과 모듈 ABI를 그대로 사용합니다.

- `PACKAGE_VALIDATION.json`: 실제 규칙 생성기 검사 21개 통과. 원본에서 네 호출 경로의 r32 거부를 재현했습니다.
- `R32_TTL_VALIDATION.json`: r32 커널의 제한된 IPv4 TCP TTL 실측입니다.
- `R32_PACKAGE_LIVE_VALIDATION.json`: r32에 호환성 패키지만 설치한 뒤의 검증입니다. r33 이미지 부팅을 뜻하지 않습니다.
- `R32_SUSTAINED_VALIDATION.json`: Mac MLO 5분 업로드·다운로드 수신 기록입니다. Air 시험이나 r33 이미지 부팅 검증은 아닙니다.
- `R32_WCID_ATTEMPT.json`: WCID 변경을 유도하지 못한 재연결 시도입니다. 즉시 가속 검사 3건 실패와 후속 복구·일시적 속도 저하를 포함합니다.
- `R32_RECOVERY_DIAGNOSTIC.json`: 재연결 직후 저하 중에도 가속이 유지된 1초 관측입니다.
- `R32_FRESH_ASSOC_SCAN.json`: 새 Mac 연결 뒤 스캔과 저하가 겹친 실시간 기록의 요약입니다. 인과 확정이나 Air 검증은 아닙니다.
- `R32_AIR_MLO_VALIDATION.json`: Air MLO 5분 실물 다운로드 결과입니다. 평균 1,979Mbps와 가속·유선 유지가 확인됐으며 장기·절전 안정성 검증은 아닙니다.
- `R32_AIR_WAKE_VALIDATION.json`: Air 절전 복귀 후 평균 1,914Mbps였지만 최저 0과 짧은 멈춤이 재현된 안정성 실패 기록입니다.
- `R32_AIR_SINGLE6_WAKE_VALIDATION.json`: Air 6GHz 단일 링크 절전 복귀의 1,860/410/2,034Mbps와 초반 일시적 저하 기록입니다. 사용자 관측은 멈춤 없이 속도만 낮아짐이며, 원래 MLO·가속 설정 복원을 검증했습니다.
- `R32_AIR_PS_WAKE_VALIDATION.json`: PS 진단을 켠 Air MLO 절전 복귀에서 1,715/1,336/1,987Mbps, 멈춤 없음이 확인됐습니다. 비정상 TX 상태가 정상 전송 중에도 관측돼 그 존재만으로 이전 멈춤 원인을 확정할 수 없습니다. 진단 기록의 출력 제한과 복원 결과를 포함합니다.
- `UPSTREAM_20260924_FIRMWARE_COMPARISON.json`: 실제 공개 UBI2 이미지와 r32 이미지의 기존 펌웨어 11개가 바이트 동일함을 검증했습니다. 새 이미지 설치 결과가 아닙니다.
- `UPSTREAM_20260924_WIFI_FIRMWARE_METADATA.json`: 실제 MT7996 WM·WA·DSP의 영역 레이아웃·암호화 다운로드 플래그입니다. 암호화된 내부 코드 검증이나 trailer CRC 검증은 포함하지 않습니다.
- `verify-image.py`: 기존 검증기에 커널·모듈 동일성 및 이미지의 실제 커널을 허용하는지 확인하는 검사를 포함합니다.

개인 설정·패킷·단말 정보는 포함하지 않습니다. Air의 과거 멈춤 해결과 장기간 안정성은 미확인입니다.
