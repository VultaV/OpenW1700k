# r32 재연결 가속 항목 정리

r30/r31에서 단말 연결이 사라진 뒤에도 이전 PPE BND 항목이 남는 것을 확인했다. r32는 AP 전체를 끄지 않고 해당 단말의 이전 브리지 흐름을 정리하고, 하드웨어 슬롯을 다시 학습할 때 새 규칙이 이전 규칙에 덮어써지는 문제를 수정하는 시험 빌드다. **설치·부팅·재연결 실기기 검증은 아직 하지 않았다.** 과거 Air의 모든 멈춤을 해결했다는 의미는 아니다.

## 변경

- mac80211은 AP/AP_VLAN 단말 제거 시 FDB 삭제 이벤트를 보낸다. netfilter는 동일 네트워크 공간·출력 포트·목적지의 이전 세대 흐름만 기존 GC로 정리한다. 현재 지원 범위인 VLAN 없는 직접 전달 브리지로 제한한다.
- 흐름 게시와 이벤트 세대를 같은 잠금으로 처리한다. 지연된 정리 작업이 이벤트 이후 게시된 새 흐름을 삭제하지 않도록 한다. 공통 teardown은 최초 실행 때만 conntrack을 정리한 뒤 재등록을 허용한다.
- Airoha PPE 등록 목록은 새 규칙이 앞에 오지만 기존 코드는 일치하는 규칙을 끝까지 덮어써 가장 오래된 목적지가 남았다. r32는 처음 일치하는 규칙 하나만 선택한다.
- 같은 물리 슬롯을 가리키는 이전 소프트웨어 연결을 해제한다. 소프트웨어 해시가 같더라도 다른 물리 슬롯에서 동작하는 연결은 유지한다. 삭제 시 현재 하드웨어 tuple과 패킷 종류를 확인해 재사용된 다른 연결을 지우지 않는다.
- L2 하위 흐름에도 실제 데이터와 해시 목록 연결을 저장한다. 수명 종료 및 통계 갱신에서 슬롯 재사용을 검사한다. INVALID/FIN 슬롯을 임의로 학습된 흐름처럼 재등록하지 않는다.
- 이전 슬롯 읽기·삭제가 실패하면 같은 규칙을 다른 슬롯에 추가하지 않는다. SRAM 오류를 포함한 최종 삭제는 기존 비동기 정리 경로의 한계를 갖는다. 완전한 오류 재시도나 펌웨어 정지는 해결한 것으로 표시하지 않는다.

새 커널 ABI는 `6.18.44-w1700k-mlo-r32`다. `struct flow_offload`에 세대 값이 추가되므로 r30/r31 모듈과 혼용하지 않는다. NPU/무선 펌웨어 바이너리는 변경하지 않는다.

## 검증

- [PPE 검사 결과](PPE_VALIDATION.json): 실제 함수와 헤더 구조체를 추출한 ASan/UBSan 검사 **11 통과 / 0 실패**. 기존 소스에서는 중복 IPv4/IPv6 규칙, 슬롯 재사용, 패킷 종류, 잘못된 슬롯 상태, 이전 슬롯 읽기 실패, L2 수명·통계 검사의 10개 실패를 재현했다. 서로 다른 물리 슬롯의 충돌 대조 검사는 기존 소스에서도 통과한다. 이는 10개의 독립적인 실기기 장애를 뜻하지 않는다.
- ARM64 PPE 객체 컴파일, 패치 적용 후 바이트 일치, checkpatch 검사 통과. checkpatch는 서명·경로 검사를 제외하고 오류·경고·체크 0개다.
- netfilter 검사: 매칭 13개, 거부 이벤트 9개, 삽입 실패 1개, 게시/이벤트 교차 실행 1,000개, teardown 3개 통과. 코어/mac80211 switchdev ON/OFF 객체 4개 통과. 자세한 범위는 [이전 후보 기록](../mlo-r30/reconnect-candidate/README.md)을 참고한다.
- 새로 패치를 적용한 빌드 트리에서도 호스트 검사를 실행한다. 이는 실제 커널 잠금·GC·NPU 동작을 대체하지 않는다.
- [전체 빌드·이미지 결과](BUILD_RESULT.json): 9개 단계 최종 통과. 모듈 74개의 r32 ABI와 패키지 206개, 펌웨어 11개 및 wpad/LuCI 파일 338개 유지를 확인했다. 최초 패키징의 로컬 샌드박스 소켓 차단은 실패 기록으로 남겼으며 일반 권한 재실행은 통과했다.

재실행:

```sh
python3 tests/test_airoha_ppe_ownership.py "$KERNEL/drivers/net/ethernet/airoha/airoha_ppe.c"
python3 tests/test_bridge_fdb_cleanup.py "$KERNEL/net/netfilter/nf_flow_table_core.c"
python3 docs/mlo-r32/verify-image.py "$BUILD" "$IMAGE" "$NEW_OUTPUT" docs/mlo-r32/build-manifest.json --baseline "$VERIFIED_R31_ARTIFACTS"
```

이미지 검사는 검증된 r31의 `build-manifest.json`과 `verified-image/` 추출 디렉터리가 필요하다. 빌드 구성은 [r32.config](r32.config), 소스·피드 해시는 [build-manifest.json](build-manifest.json)에 보존했다. 이미지의 `/etc/w1700k-mlo-repair`에는 이 공개 manifest를 넣었다. 장비별 설정을 추가하지 않는다.

## 남은 실기기 확인

부팅과 전체 모듈 ABI, 유선 연속성, 실제 WCID가 바뀌는 재연결, 다른 단말 유지, 가속 삭제·재학습, Air 업로드와 장기간 반복이 남아 있다. in-flight HW 등록/삭제의 순서와 conntrack HW 표시 상태도 별도로 확인해야 한다. FDB 이벤트 할당 실패는 기존 만료에 의존하며 정리는 동기 즉시 삭제가 아니다. VLAN·라우팅 확장, NPU 펌웨어 교체, 절전 강제 해제는 포함하지 않았다.
