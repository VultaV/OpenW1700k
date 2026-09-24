# MLO r33 패키징 검증

r32 이미지에 포함된 가속 패키지가 r30 커널만 허용하던 오류를 수정합니다. `bridge-flow-offload 1.0-r3`는 TTL 실측을 통과한 r30·r32 커널만 허용합니다. r33은 r32 커널과 모듈 ABI를 그대로 사용합니다.

- `PACKAGE_VALIDATION.json`: 실제 규칙 생성기 검사 21개 통과. 원본에서 네 호출 경로의 r32 거부를 재현했습니다.
- `R32_TTL_VALIDATION.json`: r32 커널의 제한된 IPv4 TCP TTL 실측입니다.
- `R32_PACKAGE_LIVE_VALIDATION.json`: r32에 호환성 패키지만 설치한 뒤의 검증입니다. r33 이미지 부팅을 뜻하지 않습니다.
- `verify-image.py`: 기존 검증기에 커널·모듈 동일성 및 이미지의 실제 커널을 허용하는지 확인하는 검사를 포함합니다.

개인 설정·패킷·단말 정보는 포함하지 않습니다. Air의 과거 멈춤 해결과 장기간 안정성은 미확인입니다.
