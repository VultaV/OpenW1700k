#!/usr/bin/env python3
"""Compile actual bridge verdict/notrack code against skb ownership counters."""
import argparse
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path, help='Prepared nf_conntrack_bridge.c')
parser.add_argument('--expect-old-bugs', action='store_true')
args = parser.parse_args()
source = args.source.read_text()
refrag = source[source.index('static unsigned int\nnf_ct_bridge_refrag('):source.index('/* Actually only slow path refragmentation')]
notrack = source[source.index('notrack:\n') + len('notrack:\n'):source.index('\n}\n', source.index('notrack:\n'))]
stub = r'''
#include <arpa/inet.h>
#include <stdint.h>
#include <stdio.h>
typedef uint16_t __be16;
#define ETH_P_IP 0x0800
#define ETH_P_IPV6 0x86dd
#define NF_DROP 0
#define NF_ACCEPT 1
#define NF_STOLEN 2
#define IP_CT_UNTRACKED 7
struct net; struct sock;
struct nf_hook_state { struct net *net; struct sock *sk; };
struct nf_bridge_frag_data { int unused; };
struct sk_buff { int frag_max_size, offset, protocol, frees, refs, pushed, ctinfo; };
#define BR_INPUT_SKB_CB(skb) (skb)
#define WARN_ON_ONCE(x) ((void)(x))
#define kfree_skb(skb) ((skb)->frees++)
#define nf_ct_bridge_frag_save(skb, data) ((void)0)
#define __skb_pull(skb, offset) ((skb)->pushed -= (offset))
#define __skb_push(skb, offset) ((skb)->pushed += (offset))
#define skb_reset_network_header(skb) ((void)0)
#define nf_br_ip_fragment(net, sk, skb, data, output) kfree_skb(skb)
#define nf_br_ip6_fragment(net, sk, skb, data, output) kfree_skb(skb)
#define nf_reset_ct(skb) ((skb)->refs = 0)
#define nf_ct_set(skb, ct, info) ((skb)->ctinfo = (info))
static int nf_ct_bridge_inner(struct sk_buff *skb, struct nf_bridge_frag_data *data, __be16 *proto) {
    *proto = htons(skb->protocol);
    return skb->offset;
}
'''
cases = r'''
int main(void) {
    int cases[][5] = {
        {0, 0, ETH_P_IP, NF_ACCEPT, 0},
        {1, -1, ETH_P_IP, NF_DROP, 1},
        {1, 0, 0x0806, NF_DROP, 1},
        {1, 0, ETH_P_IP, NF_STOLEN, 1},
        {1, 0, ETH_P_IPV6, NF_STOLEN, 1}
    };
    struct nf_hook_state state = {0};
    int errors = 0;
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        struct sk_buff skb = {.frag_max_size=cases[i][0], .offset=cases[i][1], .protocol=cases[i][2]};
        int verdict = nf_ct_bridge_refrag(&skb, &state, NULL);
        /* nf_hook_slow owns the skb when a hook returns NF_DROP. */
        if (verdict == NF_DROP) kfree_skb(&skb);
        errors += verdict != cases[i][3] || skb.frees != cases[i][4];
    }
    for (int refs = 0; refs <= 1; refs++) {
        struct sk_buff skb = {.refs=refs, .pushed=-4};
        int verdict = run_notrack(&skb, 4);
        errors += verdict != NF_ACCEPT || skb.refs != 0 || skb.pushed != 0 || skb.ctinfo != IP_CT_UNTRACKED;
    }
    printf("%d ownership failures across 7 cases\n", errors);
    return errors;
}
'''
with tempfile.TemporaryDirectory(prefix='bridge-owner-') as directory:
    path = Path(directory)
    code = path / 'check.c'
    code.write_text(stub + refrag + '\nstatic int run_notrack(struct sk_buff *skb, int offset) {\n' + notrack + '\n}\n' + cases)
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Werror', '-O1', str(code), '-o', str(path/'check')], check=True)
    result = subprocess.run([str(path/'check')], capture_output=True, text=True)
    print(result.stdout, end='')
    expected = 3 if args.expect_old_bugs else 0
    assert result.returncode == expected, (result.returncode, result.stderr)
    print('PASS: old defects reproduced' if expected else 'PASS: drop, stolen, accept and conntrack ownership')
