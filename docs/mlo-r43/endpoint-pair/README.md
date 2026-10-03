# r43 양단 캡처 도구 인계용 소스 스냅샷

2026-10-03에 당시 로컬 소스를 보존했다. `.txt` 파일은 **실행용 배포물이 아닌 코드 검토용 기록**이다. 로컬 원본은 `artifacts/npu-zero-budget-r43-2026-09-27/endpoint-pair/`에 유지한다. 원본은 변경하지 않았다.

## 포함한 작업

- `mac-capture.sh.txt`: Mac 일반 Wi-Fi 인터페이스에서 시험의 두 endpoint/TCP 5203만 캡처한다. root/사용자 소유권, 유선 관리 경로, 공간, 기존 결과, 프로세스 신원 검사와 170초 종료/stop marker/회전 한도를 포함한다. 모니터 모드나 네트워크 설정을 변경하지 않는다.
- `check-capture.py.txt`: 실제 root/BPF/네트워크 대신 명령을 모의 대체하는 12개 로컬 회귀 시험이다.
- `check-pair.py.txt`: 서버와 Mac의 TCP sequence 범위 및 ACK 시각을 시계 경계로 비교한다. GSO/LRO 때문에 패킷 수를 일대일 대응시키지 않는다. 빈 캡처, drop, 회전 누락/마지막 파일, 잘못된 sequence 범위를 거부한다.
- `run.py.txt`: 기존 r43 60초 시험의 어댑터다. 캡처 시작 이후 40초 arming/50초 실행 준비 한도, 서버 준비 nonce, 600초 사용자 캡처 대기, 중단 시 캡처 종료를 포함한다.

## 재개할 때의 경계

실제 양단 캡처 시험은 완료되지 않았다. 이전 시작 시도는 준비 시간 초과/빈 캡처로 중단됐다. `PREPARATION_RESULT_20260927.json`은 **9월 27일 당시 준비 검사 기록**이며 지금 실행 가능하다는 판정이 아니다. 새 장치/주소/유선 인터페이스/설치 빌드/권한/디스크 상태를 재확인해야 한다. 캡처는 짧은 payload 조각과 식별자를 포함할 수 있으므로 결과를 공개하지 않는다.

`run.py`는 `../ps-repeat/run.py` 및 그 재귀 의존성의 해시를 고정한다. `check-pair.py`는 `../check-repeat.py`, 다른 r42 clock/alignment 도구 및 decoder의 해시를 고정한다. 이 기록만 복사해서 실행할 수 없다. 필요한 의존성은 기존 로컬 artifacts에 있으며, 부팅 ID와 단말 식별자를 포함한 설치 증거/원시 기록은 공개 범위에서 제외했다. 원본의 해시 검사를 우회하거나 준비 실패 조건을 지우지 않는다.

절대 사용자 경로를 `<LOCAL_WORKSPACE>`로, 실제 LAN 주소/대역을 RFC 5737 문서용 `192.0.2.0/24` 값으로 치환했다. 로컬 원본과 공개 사본의 차이는 이 치환뿐이다. 따라서 아래 공개 사본 해시는 원본의 고정 의존성 해시를 대체하지 않는다. `.txt` 확장자를 제거해 실기기에 실행하지 않는다.

## 2026-10-03 오프라인 재검증

- `check-pair.py --self-test`: PASS, 음성 대조 6개 포함.
- `run.py --self-test`: PASS, 준비 시각 경계/잘못된 세션·세대 표식 5개 거부 포함. 장치 호출 없음.
- `check-capture.py`: **FAIL**. 기본 샌드박스의 `/bin/ps` 차단을 제거해 재실행한 뒤에도 첫 `deadline` 모의 시험이 `status=FAILED, reason=deadline, tcpdump_exit=0`으로 끝났다. 정상 종료를 기대한 assertion이 실패하여 이후 사례는 실행되지 않았다. 9월 27일의 12 PASS 기록을 현재 결과로 재사용하지 않는다. 종료 제어/프로세스 검사 경로를 재검증하기 전 실기기 실행 준비 완료로 보지 않는다.
- 현재 실행한 명령 기준: 2 PASS / 1 FAIL. 실제 양단 캡처/무선 시험: 미실시.

이 검사는 실기기 BPF 캡처, 펌웨어 수정 효과 또는 원래 멈춤 증상의 해결을 입증하지 않는다.

## 파일 무결성

| 원본 파일 | 로컬 원본 SHA256 | 공개 `.txt` SHA256 |
|---|---|---|
| `mac-capture.sh` | `f1cdb93d9f839e4f5e99d6e47fc8321cbc0ad7bbcd46fb1d780d22eeffe85615` | `1d53b8316f25c16f74bc6ee21a274e448a74f9695f8c023c0b00269e7fd6baf1` |
| `check-capture.py` | `511a8b8dad6fabafe5407ee3036ce2c8396ed67d366e00fc83d5ab454be76850` | `5224de161f752cfbf6fc5a803bf09d2d44cfc14e938fe7ed5701d2c1faeed69a` |
| `check-pair.py` | `ebfc20bb07a079fb4b7c295641880b6a4b4869378fb892ad807e2d96955b6f22` | `ebfc20bb07a079fb4b7c295641880b6a4b4869378fb892ad807e2d96955b6f22` |
| `run.py` | `c9a1689696f341ce5004d85bfc61b34caff09c90ec491d6d2b95fa0025c3cbde` | `c9a1689696f341ce5004d85bfc61b34caff09c90ec491d6d2b95fa0025c3cbde` |
