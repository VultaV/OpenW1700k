# 2.4GHz IPv6 / Matter 확인 — 2026-09-27

**OpenWrt_2G에서 로컬 IPv6 주소 자동 설정, 공유기 통신, Matter 및 Thread 서비스 발견을 확인했다. 공유기 설정은 변경하지 않았다.**

Mac을 2.4GHz에 직접 연결해 검사했다. 2.4GHz AP는 유선과 같은 br-lan이며 LAN IPv6가 활성화돼 있다. RA의 /64 on-link·SLAAC prefix가 실제 패킷에 나타났고, Mac이 해당 IPv6 주소를 받았다. 공유기 링크 로컬 ping은 3/3, IPv6 웹 요청은 HTTP 200이었다. AP 포트 자체의 disable_ipv6=1은 이 구성에서 L3를 br-lan이 담당하는 것과 양립하며, 이 값만으로 Wi-Fi IPv6 차단을 뜻하지 않는다.

| 항목 | 결과 |
|---|---|
| 유선 ↔ 2.4GHz 분리 | 동일 브리지, 포트 isolation 꺼짐 |
| RA / SLAAC / DHCPv6 | 활성, RA·주소 수신 확인 |
| IPv6 mDNS | 2.4GHz에서 질의·응답 확인 |
| Matter 운영 서비스 `_matter._tcp` | Mac Wi-Fi와 유선 양쪽에서 발견 |
| Thread `_meshcop._udp` | Nest Hub가 양쪽에서 발견됨 |
| Nest Hub IPv6 TCP | HTTP 404 응답 확인: 네트워크 접속 성공, 해당 HTTP 경로는 없음 |
| 캡처 | 456 + 118 records, kernel drop 0; 브리지 중복 포함 |

WAN6는 현재 대기 상태이고 인터넷용 IPv6 prefix/default route가 없다. 이에 따라 OpenWrt RA의 default-router lifetime은 0이지만 로컬 prefix는 유효하다. Matter에는 로컬 IPv6와 mDNS가 필요하며 인터넷 IPv6 자체는 필수가 아니다. [Home Assistant 공식 문서](https://www.home-assistant.io/integrations/matter/)

Nest Hub의 Thread 경로 광고도 관측했다. 실제 Matter 페어링·인증된 기기 제어, HA 호스트가 Thread route를 받아들이는지, Thread 말단 기기 도달 여부는 이번 검사 범위에 포함하지 않았다. Nest Hub ping은 12초 내 응답이 없었으나 동일 장치 IPv6 TCP는 응답했다. 별도 태블릿 ping 명령은 인자 오류로 무효이며 성공으로 계산하지 않았다.

검사 12 PASS / 0 FAIL, 별도 주의사항 2 / 미실시 2. 수행한 검사 통과율 100%이며 Matter 전체 기능의 완료 판정은 아니다. 원시 주소·식별자·패킷은 private 폴더에만 보존한다.
