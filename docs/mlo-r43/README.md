# r43 NPU zero-budget guard

NPU 송신 worker가 ring 여유 7일 때 consumer에 예산 0을 넘길 수 있고, consumer는 첫 처리 후 이를 unsigned 최대값으로 감소시킵니다. 다른 종료 조건도 있으므로 무한 루프라고 단정하지 않습니다. 이 결함이 실제 Air 멈춤을 일으켰는지는 아직 확인되지 않았습니다.

r43은 부팅 로더에서 **정확한 program/data SHA256 쌍**을 확인하고, 코어를 시작하기 전 프로그램 DRAM 복사본의 4바이트만 바꿉니다. 0 예산이면 기존 반환 경로를 사용하며, 양수 예산 경로는 유지합니다. program 전체 readback 해시가 다르면 코어 시작 전에 실패합니다. 다른 펌웨어 쌍에는 적용하지 않습니다. 파일 이름으로 판단하지 않으며 원본 펌웨어 파일은 바꾸지 않습니다.

- program: `e743d1b59a9ca6d043e38ff71075e8d28702a104b94abb17a4035514efda4643`
- data: `61a75afb052feed2ceb2f3023e16f50317c05c78f9c8e564bf01924ce39c7ec1`
- 적용 위치: `0x9e1a`, `9374f50f → e284e1c5`
- DRAM program 예상 SHA256: `389cfecb074fc21c163006c791b65f9628fe790cfb682f2e288b71c14104a736`

실제 함수 추출 검사는 원본 1건·후보 24건을 macOS CommonCrypto 및 ASan/UBSan으로 확인합니다. firmware 요청·MMIO·IRQ 등은 host fixture이며 실제 하드웨어 검사를 대신하지 않습니다. RV32 제한 구간 검사는 정상 band 0·1의 양수 입력 131,082건과 0 입력 2건을 확인했습니다. 전체 펌웨어 에뮬레이션은 아닙니다. 기존 같은 index store의 동시성 범위는 [분석 기록](../npu-budget-guard-20260926/CONCURRENCY_REVIEW.md)에 있습니다.

소스 패치는 DT와 기본 firmware 선택이 공유하는 loader에 적용합니다. 설치 파일의 ABI는 `6.18.44-w1700k-mlo-r32`를 유지하고 `kmod-airoha-npu`만 r3에서 r4로 올립니다. 이미지·설치·실기기 결과는 각각의 검증 기록으로 구분합니다.

이 변경은 부팅 경로 전용입니다. 실행 중 NPU 메모리 수정, unbind/rebind, 모듈 재적재의 안전성을 제공하지 않습니다. `applied` 로그나 모듈 bound만으로 정상 작동을 인정하지 않고, 새 부팅의 NPU version 응답과 실제 가속 전송을 추가 확인해야 합니다. Mac 시험 성공을 Air 절전 복귀 문제 해결로 간주하지 않습니다.
