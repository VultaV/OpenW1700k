# 초기 builds 작업 사본의 미공개 변경 보존

2026-10-03 검토에서 `builds/`의 수정 사항이 별도 GitHub 브랜치에 게시되지 않은 것을 확인하여 원본 diff와 회귀 시험을 보존한다. 이는 **과거 작업의 보존본**이며 현재 r43 펌웨어 트리에 적용한 변경이 아니다.

- 원본: [w1700k/builds](https://github.com/w1700k/builds)
- 기준 커밋: `9449e4ca242ab30278df20940d6654ddc1c102e8`
- 로컬 브랜치: `codex/build-and-updater-fixes`
- `pending-builds.patch`: 변경된 추적 파일 8개의 전체 diff.
- `tests/`: 미추적 회귀 시험 4개와 공개 GitHub 릴리스 메타데이터 fixture 1개.

## 변경 내용과 현재 펌웨어의 관계

4개 fastbuild workflow는 다운로드 HTTP 오류, 소스 가져오기/checkout 오류, download/custom 단계 실패 및 모든 compile 재시도 실패를 실패로 전달한다. self-hosted workflow는 이전 출력/컨테이너를 정리한 뒤 작업 디렉터리를 준비한다. `custom.sh`에는 실패 즉시 종료를 추가했다.

GitHub 펌웨어 다운로드 CGI는 인증된 POST, 정확한 이미지 선택, SHA256 및 sysupgrade 호환성 검증, 오류 보존을 사용한다. 이 CGI 파일들은 이미 공개된 r29/r30 overlay와 동일하다. 초기 UI 수정은 오류 전파/인증 요청/안전한 외부 링크를 추가했지만, 현재 r43에서는 [r34 feed patch](../mlo-r34/feed-patches/0003-luci-attendedsysupgrade-github-update.patch)가 upstream의 정상 fallback까지 보존하는 후속판이다. 이 역사적 `overview.js` diff를 r43에 덮어쓰지 않는다.

기준 커밋의 별도 checkout에 patch를 적용하고 tests를 복사해야 원래 검사 경로가 맞는다. `git apply --check pending-builds.patch`로 먼저 확인한다. 원본 로컬 `builds/`와 펌웨어용 `publish-mlo-r29/`를 혼합하지 않는다.

## 2026-10-03 로컬 재검증

실제 장치, 네트워크 다운로드, 펌웨어 설치 명령은 모의 대체했다.

- `python3 tests/test_workflows.py`: 53개 PASS.
- `python3 tests/test_custom.py`: 4개 PASS.
- `node tests/test_github_updater_ui.js`: 5개 PASS.
- `python3 tests/test_github_updater.py`: 20개 updater 시나리오 PASS, UI 5개도 내부 호출하여 PASS. 중복 UI 결과를 별개 커버리지로 합산하지 않는다.

GitHub Actions 원격 빌드가 이 보존본으로 성공했다는 뜻은 아니다. `.DS_Store`, 캐시, 비밀번호, 실기기 설정/패킷은 포함하지 않았다.
