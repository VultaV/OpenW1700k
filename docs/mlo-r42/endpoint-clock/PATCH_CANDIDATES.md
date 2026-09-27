2026-09-27 읽기 전용 검토 결과다. **아래 업데이트는 아직 반영하지 않았다.** MLO·PS 정체 수정으로 확인된 변경이 아니라 진단 도구의 보안·유지보수 업데이트 후보다.

공식 변경은 [libpcap 1.10.7 — b36d01c69682adf3eaf00f9e9414e99a6d0a0d41](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/b36d01c69682adf3eaf00f9e9414e99a6d0a0d41)과 [tcpdump 4.99.7 — b6bb254a85fe375cf923bc9da3eeceefd1526889](https://github.com/OpenWRT-fanboy/OpenW1700k/commit/b6bb254a85fe375cf923bc9da3eeceefd1526889)이다. 현재 포크의 대상 7개 파일은 모두 공식 변경 직전 파일과 Git blob SHA가 일치한다. 최소 반영 범위는 다음과 같다.

```text
package/libs/libpcap/Makefile
package/libs/libpcap/patches/100-no-openssl.patch
package/libs/libpcap/patches/102-skip-manpages.patch
package/libs/libpcap/patches/300-Add-support-for-B.A.T.M.A.N.-Advanced.patch
package/network/utils/tcpdump/Makefile
package/network/utils/tcpdump/patches/001-remove_pcap_debug.patch
package/network/utils/tcpdump/patches/100-tcpdump_mini.patch
```

현재 recipe는 libpcap 1.10.6·tcpdump 4.99.6이다. 새 recipe는 패키지 의존성을 추가하지 않으며 libpcap ABI major 1, OpenSSL 제외 패치, tcpdump의 `--without-crypto`·`--without-cap-ng`를 유지한다. libpcap 소스 압축 형식의 gzip→xz 변경은 기존 압축 해제 코드가 지원한다. 원격 캡처는 계속 비활성화하고 `rpcapd`를 추가하지 않는 범위다. tcpdump 회귀시험도 기존 Perl 기본 모듈을 사용하며 새 테스트 패키지 의존성은 확인되지 않았다.

**현재 r42 이미지의 빌드 설정과 추출한 APK 목록에는 libpcap·tcpdump·tcpdump-mini·rpcapd가 없다.** 기존 임시 진단 도구는 이미지와 별도로 준비한 바이너리다. 따라서 recipe 갱신만으로 현재 도구가 교체되지는 않으며, 이 변경만으로 당장 펌웨어 버전을 올리거나 설치할 근거도 없다.

다음 단계의 최소 범위는 위 7개 recipe 파일 반영 후 libpcap·tcpdump 진단 도구만 별도로 빌드·검증하는 것이다. 패키지 선택이나 상주 서비스를 추가할 필요는 없다. 반영 전후 검증에는 다음이 필요하다.

- 배포 소스 해시, 패치 적용 결과, 대상 아키텍처·동적 라이브러리 의존성과 새 바이너리 해시 확인.
- 기존 캡처 fixture로 BPF 컴파일·필터 선택·패킷 길이 및 분석 결과 비교. 새 libpcap은 잘못된 BPF에 대한 검증을 강화하므로 기존 결과를 자동 승계하지 않는다.
- 기존 netlink live/offline 길이 계약을 각각 재검증. 이번 변경은 해당 차이를 없앤다는 근거가 아니다.
- 새 도구를 사용하는 관측 가드의 해시 고정값 검증. 과거 증거·스크립트를 덮어쓰거나 기존 해시와 새 바이너리를 혼용하지 않는다.

이번 검토에서는 소스 적용, 빌드, 회귀시험 실행 또는 장치 변경을 하지 않았다. 향후 패키지 빌드 성공만으로 upstream 회귀시험이나 실기기 캡처까지 통과했다고 기록하지 않는다.
