"""Run the candidate's actual recovery block with boundary/failure cases."""
from pathlib import Path
import subprocess
import tempfile

patch = Path(__file__).resolve().parents[1] / 'package/network/services/hostapd/patches/9999-reset-expired-mld-before-link-setup.patch'
block = '\n'.join(line[1:] for line in patch.read_text().splitlines()
                  if line.startswith('+') and not line.startswith('+++')) + '\n'
stub = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;
#define WLAN_STA_AUTH 1u
#define WLAN_STA_ASSOC 2u
#define WLAN_STA_AUTHORIZED 32u
#define WLAN_STA_MFP 1024u
#define WLAN_AUTH_OPEN 0
#define WLAN_AUTH_SAE 3
#define WLAN_STATUS_AP_UNABLE_TO_HANDLE_NEW_STA 17
#define WPA_DRV_STA_REMOVED 9
#define FULL_AP_CLIENT_STATE_SUPP(f) ((f) & 1)
struct hostapd_iface { int drv_flags; };
struct hostapd_data { struct hostapd_iface *iface; bool mld; };
struct sta_info { u32 flags; int sa_query_timed_out, added_unassoc, auth_alg; void *wpa_sm; };
static int resets, events, failure;
#define ap_sta_is_mld(h,s) ((void)(s), (h)->mld)
static int ap_sta_re_add(struct hostapd_data *h, struct sta_info *s) {
    (void)h;
    resets++;
    s->flags &= ~(WLAN_STA_AUTH | WLAN_STA_ASSOC | WLAN_STA_AUTHORIZED);
    if (failure) return failure;
    s->added_unassoc=1;
    return 0;
}
static int wpa_auth_sm_event(void *sm, int event) {
    assert(sm==(void*)1 && event==WPA_DRV_STA_REMOVED);
    assert(resets==1); events++; return 0;
}
static int recover(struct hostapd_data *hapd, struct sta_info *sta) {
    int resp=0;
'''
main = r'''
fail:
    return resp;
}
int main(void) {
    unsigned cases=0;
    for (unsigned mask=0; mask<128; mask++)
    for (int alg=0; alg<6; alg++)
    for (int fail_case=0; fail_case<2; fail_case++) {
        struct hostapd_iface iface={.drv_flags=!!(mask&1)};
        struct hostapd_data h={.iface=&iface,.mld=!!(mask&2)};
        struct sta_info s={.flags=2u|32768u|((mask&4)?1u:0u)|((mask&8)?32u:0u)|((mask&16)?1024u:0u),
            .sa_query_timed_out=!!(mask&32), .added_unassoc=!!(mask&64), .auth_alg=alg, .wpa_sm=(void*)1};
        u32 flags=s.flags;
        int added=s.added_unassoc;
        bool wanted=iface.drv_flags && h.mld && (mask&8) && (mask&16) && (mask&32) && !(mask&64) && (alg==0 || alg==3);
        resets=events=0; failure=fail_case?-12:0;
        int result=recover(&h,&s);
        assert(resets==(wanted?1:0));
        assert(events==(wanted && !failure?1:0));
        assert(result==(wanted && failure?17:0));
        if (!wanted) assert(s.flags==flags && s.added_unassoc==added);
        else if (!failure) assert(s.flags==(flags&~(2u|32u)) && s.added_unassoc==1);
        cases++;
    }
    printf("PASS %u recovery guard and allocation-failure cases\n",cases);
}
'''
with tempfile.TemporaryDirectory(prefix='hostapd-reassoc-check-') as tmp:
    path = Path(tmp) / 'check.c'
    path.write_text(stub + block + main)
    exe = path.with_suffix('')
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    '-DCONFIG_IEEE80211BE', str(path), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
