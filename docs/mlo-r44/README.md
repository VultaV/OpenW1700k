# r44 호스트 측 보안·정확성 수정

r43의 커널·모듈·무선/NPU 펌웨어는 그대로 두고, 이미지의 사용자 영역만 고친 버전입니다.
MLO 간헐 멈춤과는 관계가 없습니다. 2026-10-03 실제 장치에 설치해 확인했습니다(`BUILD_RESULT.json`의
`device_validation`). 나머지 실기 확인 항목은 [호스트 측 수정 기록](../host-fixes-20261003/README.md) 5절에 있습니다.

## 바뀐 점

- 보드 LuCI 앱의 root 실행 경로 제거: netspeedtest `arch` 주입, flowsense awk 실행, `/dev/mem` ACL,
  NPU PLL 상한(순정 1200 MHz, 정수 넘침 우회 차단), 팬 수동 모드 고정, wifi7 ACL 그룹 분리(F01).
- UCI·런타임·GitHub 문자열을 텍스트로 표시(wifi7, MLO, 팬, FlowSense, 업데이트 화면의 XSS)와
  백엔드 JSON 형식 보장.
- wifi7: 실패한 UCI 쓰기 뒤 재시작 중단(F05), 보이는 프로필 편집(F07), 실제 netdev 사용(F08),
  저장값 되돌리기, 목록에 없는 암호화 값·사용자 지정 네트워크 유지(이전에는 Networks 탭 저장이
  `psk2+ccmp` 등을 개방 AP로 바꿀 수 있었음). MLO: 비활성 프로필 저장(F06).
- 표준 무선 페이지의 다중 라디오 MLO 보호(LuCI 피드 패치 0004)와, 비활성 섹션의 한 칸짜리 `device` 목록 때문에
  페이지가 TypeError로 열리지 않던 upstream 결함 수정(luci-base 피드 패치 0006, 장치에서 재현·확인).
- sysupgrade: FIT 해시(`fit_check_sign`)와 W1700K UBI2 FIT 배치(`w1700k-fit-check`)를 검사하고,
  맞지 않는 이미지는 `-F`로도 거부합니다.
- GitHub 업데이터: 저장소 `VultaV/OpenW1700k`, `SHA256SUMS`, 설정 유지 여부 반영. 이미지의 jq에는
  정규식이 없어 r29–r43의 업데이터는 장치에서 항상 403/502로 끝났습니다. 정규식 없이 검사합니다.
- 원격 apk 피드 제거(커널 ABI가 다른 snapshot kmod 설치 방지), ca-certificates 재빌드 중복 수정,
  r43이 실제로 쓰던 채널 분석 패치(`998-single-wiphy.patch`) 보존.

커널 `6.18.44-w1700k-mlo-r32`, 모듈 74개, 펌웨어 11개, wpad는 r43과 바이트 단위로 같습니다
(검증 결과는 `BUILD_RESULT.json`). 새로 들어간 패키지는 `w1700k-fit-check`와 `libfdt`입니다.

## 설치 후 후속 소스 수정

설치된 r44에서 확인한 두 표시 문제를 고쳤습니다. 다음 변경은 기존 이미지·검증 기록에
포함되지 않은 소스 수정이며, 새 펌웨어 빌드·배포·설치와 실제 브라우저 확인은 하지 않았습니다.

- WiFi 7(`PKG_RELEASE=20261004`): `hostapd_cli stat` 출력이 없으면 `iw info`·`station dump`로
  링크 카드 값을 채우고, MLO 링크의 대역을 주파수로 구분합니다. 없는 `sku_disable` 파일을
  SKU 제한 해제로 판단하지 않습니다.
- 채널 분석: 보존한 998 뒤에 `999-mlo-scan-notice.patch`를 적용합니다. 별도 활성 non-MLD netdev가
  없는 MLO 전용 라디오는 빈 스캔 대신 스캔 불가 사유를 표시하며, 2.4 GHz 스캔은 유지합니다.

## 알려진 제약

- 이 드라이버의 MLO 구성에서는 5·6 GHz 스캔을 할 수 없습니다. 후속 999는 해당 탭에서 이 제약을
  안내합니다. 드라이버 스캔 기능과 MLO 간헐 멈춤의 해결 여부는 바뀌지 않았습니다.
- 후속 수정의 WiFi 7 카드·SKU 경고와 채널 분석 안내·폴링 동작은 실제 브라우저 확인이 남아 있습니다.

## 빌드

[호스트 측 수정 기록](../host-fixes-20261003/README.md) 7절의 순서를 따르되, config와 manifest만 r44 것을 씁니다.

```sh
cp docs/mlo-r44/r44.config .config
make defconfig        # CONFIG_PACKAGE_w1700k-fit-check=y, CONFIG_PACKAGE_libfdt=y 확인
rm -rf files && mkdir files && cp -R docs/mlo-r30/overlay/* files/
cp docs/mlo-r44/build-manifest.json files/etc/w1700k-mlo-repair
make -j"$(nproc)"
```

`build-manifest.json`의 `built_source_commit`은 빌드한 코드 커밋입니다. 이 문서들은 그 위에 따로 커밋했습니다.

## 설치 전 확인

이 이미지를 설치하면 이후 sysupgrade는 FIT 검사를 통과해야 합니다. 이 Mac의 W1700K sysupgrade
이미지 60개는 모두 `fit_check_sign`을, 58개는 `w1700k-fit-check`를 통과했지만 장치에서 실행한 적은
없습니다. 처음 설치할 때는 유선 관리 경로와 시리얼/U-Boot 복구 수단을 준비하고, 설치 뒤 바로
다음을 확인하세요.

- `sysupgrade -T` 로 이 이미지와 r43 이미지(`562c6bae…`)가 모두 통과하는지
- LuCI 로그인, 무선 페이지, wifi7·MLO·팬·FlowSense·업데이트 화면, 무선·MLO 기동과 가속 flow
- `/etc/apk/repositories.d/distfeeds.list`에 원격 주소가 없는지

막히면 검증된 r43으로 내려갈 수 있습니다(r43에서는 `-F`가 다시 동작합니다).
