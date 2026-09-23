#!/usr/bin/env python3
"""Check bridge TTL source guards in a prepared kernel tree using a host C compiler.

Usage: python3 tests/test_bridge_ttl.py /path/to/linux-6.18.44
Requires Python 3 and cc (or CC). No generated kernel configuration is required.
This compiles extracted source fragments with stubs, not the kernel or driver.
It cannot prove checksum correctness, actual fallback forwarding, module ABI
isolation, or the hardware meaning of the PPE bit. Run target and packet tests.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

LIMITATIONS = [
    "Extracted guards only; not a kernel build or full forwarding test.",
    "IPv4 checksum helper and kernel context are stubs.",
    "Does not prove PPE bit semantics, packet checksums, or module ABI isolation.",
]


def run_checks(kernel, compiler, checks):
    def check(name, passed):
        if not passed:
            raise AssertionError(name)
        checks.append(name)

    def read(name):
        return (kernel / name).read_text()

    def one(pattern, source, name):
        matches = re.findall(pattern, source, re.S)
        if len(matches) != 1:
            raise AssertionError(f"{name}: expected one source fragment, found {len(matches)}")
        return matches[0]

    def enum_text(name, source):
        return one(r'(enum ' + name + r' \{.*?\n\};)', source, name)

    flow_h = 'include/net/flow_offload.h'
    nf_h = 'include/net/netfilter/nf_flow_table.h'
    ip = read('net/netfilter/nf_flow_table_ip.c')
    nft = read('net/netfilter/nft_flow_offload.c')
    offload = read('net/netfilter/nf_flow_table_offload.c')
    ppe = read('drivers/net/ethernet/airoha/airoha_ppe.c')

    family = one(r'(\tif \(nft_pf\(pkt\) == NFPROTO_BRIDGE\)\n\t\t__set_bit\(NF_FLOW_BRIDGE, &flow->flags\);)', nft, 'bridge-family classification')
    v4 = one(r'(\tif \(!test_bit\(NF_FLOW_BRIDGE, &flow->flags\)\)\n\t\tip_decrease_ttl\(iph\);)', ip, 'IPv4 TTL guard')
    v6 = one(r'(\tif \(!test_bit\(NF_FLOW_BRIDGE, &flow->flags\)\)\n\t\tip6h->hop_limit--;)', ip, 'IPv6 hop-limit guard')
    v4early = one(r'(\tif \(iph->ttl <= 1\)\n\t\treturn -1;)', ip, 'IPv4 low-TTL fallback')
    v6early = one(r'(\tif \(ip6h->hop_limit <= 1\)\n\t\treturn -1;)', ip, 'IPv6 low-hop-limit fallback')
    alloc = one(r'(static inline struct flow_action_entry \*\nflow_action_entry_next\(.*?\n\})', offload, 'action allocator')
    keep = one(r'(\tif \(test_bit\(NF_FLOW_BRIDGE, &flow->flags\)\) \{.*?entry->id = FLOW_ACTION_KEEP_TTL;\n\t\})', offload, 'KEEP_TTL action emission')
    accept = one(r'(\t\tcase FLOW_ACTION_KEEP_TTL:.*?\n\t\t\tbreak;)', ppe, 'PPE action parser')
    clear = one(r'(\tif \(keep_ttl\)\n\t\thwe.ib1 &= ~AIROHA_FOE_IB1_BIND_TTL;)', ppe, 'PPE bit override')

    actions = re.sub(r'/\*.*?\*/', '', enum_text('flow_action_id', read(flow_h)), flags=re.S)
    flags = enum_text('nf_flow_flags', read(nf_h))
    check('KEEP action appended before sentinel', bool(re.search(r'FLOW_ACTION_CONTINUE,\s*FLOW_ACTION_KEEP_TTL,\s*NUM_FLOW_ACTIONS,', actions)))
    check('bridge flag appended', bool(re.search(r'NF_FLOW_HW_ESTABLISHED,\s*NF_FLOW_BRIDGE,\s*\};', flags)))
    check('bridge classification precedes flow publication', nft.index(family) < nft.index('ret = flow_offload_add(flowtable, flow);'))
    check('only one IPv4 TTL decrement in shared source', ip.count('ip_decrease_ttl(iph);') == 1)
    check('only one IPv6 hop-limit decrement in shared source', ip.count('ip6h->hop_limit--;') == 1)
    common_start = offload.index('nf_flow_rule_route_common(')
    common_end = offload.index('int nf_flow_rule_route_ipv4', common_start)
    check('KEEP emission belongs to common builder', keep in offload[common_start:common_end])
    check('KEEP allocation precedes redirect ownership', offload.index(keep) < offload.index('if (flow_offload_redirect(', common_end))
    check('PPE KEEP state defaults off', 'bool keep_ttl = false;' in ppe)
    prepare_pos = ppe.index('err = airoha_ppe_foe_entry_prepare(')
    check('PPE override follows successful prepare', ppe.index(clear) > ppe.index('if (err)\n\t\treturn err;', prepare_pos))
    check('PPE override precedes commit', ppe.index(clear) < ppe.index('err = airoha_ppe_foe_flow_commit_entry(', prepare_pos))

    nfproto_enum = one(r'(enum \{\n\s*NFPROTO_UNSPEC.*?\n\};)', read('include/uapi/linux/netfilter.h'), 'NFPROTO enum')
    dissector_enum = enum_text('flow_dissector_key_id', read('include/net/flow_dissector.h'))
    cap_line = one(r'(#define NF_FLOW_RULE_ACTION_MAX\s+24)\b', offload, '24-action capacity')
    bit_line = one(r'(#define AIROHA_FOE_IB1_BIND_TTL\s+BIT\(24\))', read('drivers/net/ethernet/airoha/airoha_eth.h'), 'PPE TTL bit constant')
    code = '''#include <assert.h>
    #include <stdbool.h>
    #include <stdint.h>
    #include <stdio.h>
    #include <errno.h>
    #define BIT(n) (1U << (n))
    #define unlikely(x) (x)
    #define test_bit(n,p) (!!(*(p) & (1UL << (n))))
    #define __set_bit(n,p) (*(p) |= 1UL << (n))
    ''' + '\n'.join([enum_text('flow_action_id', read(flow_h)), enum_text('nf_flow_flags', read(nf_h)), nfproto_enum, dissector_enum, cap_line, bit_line]) + '''
    struct flow_offload { unsigned long flags; };
    struct nft_pktinfo { unsigned int pf; };
    static unsigned int nft_pf(const struct nft_pktinfo *p) { return p->pf; }
    struct iphdr { uint8_t ttl; };
    struct ipv6hdr { uint8_t hop_limit; };
    static void ip_decrease_ttl(struct iphdr *p) { --p->ttl; }
    struct flow_action_entry { enum flow_action_id id; };
    struct flow_rule { struct { unsigned int num_entries; struct flow_action_entry entries[NF_FLOW_RULE_ACTION_MAX]; } action; };
    struct nf_flow_rule { struct flow_rule *rule; };
    ''' + alloc + '''
    static unsigned long classify(unsigned int pf, unsigned long initial) {
     struct nft_pktinfo packet = { .pf = pf }; const struct nft_pktinfo *pkt = &packet;
     struct flow_offload object = { .flags = initial }; struct flow_offload *flow = &object;
    ''' + family + '''
     return object.flags;
    }
    static int v4_guard(struct iphdr *iph, struct flow_offload *flow) {
    ''' + v4early + '\n' + v4 + '''
     return 0;
    }
    static int v6_guard(struct ipv6hdr *ip6h, struct flow_offload *flow) {
    ''' + v6early + '\n' + v6 + '''
     return 0;
    }
    static int emit_keep(struct flow_offload *flow, struct nf_flow_rule *flow_rule) {
    ''' + keep + '''
     return 0;
    }
    static int apply_keep(unsigned int addr_type, int copies, uint32_t *ib1) {
     bool keep_ttl = false;
     struct { uint32_t ib1; } hwe = { .ib1 = *ib1 };
     for (int i = 0; i < copies; ++i) {
      switch (FLOW_ACTION_KEEP_TTL) {
    ''' + accept + '''
      default: return -EOPNOTSUPP;
      }
     }
    ''' + clear + '''
     *ib1 = hwe.ib1;
     return 0;
    }
    static unsigned int passed;
    #define CHECK(c) do { if (!(c)) { fprintf(stderr,"failed line %d: %s\\n",__LINE__,#c); return 1; } ++passed; } while (0)
    int main(void) {
     const unsigned int families[] = { NFPROTO_UNSPEC, NFPROTO_INET, NFPROTO_IPV4, NFPROTO_ARP, NFPROTO_BRIDGE, NFPROTO_IPV6, NFPROTO_NETDEV };
     for (unsigned int i = 0; i < sizeof(families)/sizeof(families[0]); ++i) {
      unsigned long existing = (1UL << NF_FLOW_SNAT) | (1UL << NF_FLOW_HW_BIDIRECTIONAL);
      unsigned long result = classify(families[i], existing);
      CHECK((result & existing) == existing);
      CHECK(!!(result & (1UL << NF_FLOW_BRIDGE)) == (families[i] == NFPROTO_BRIDGE));
     }
     for (unsigned int bridge = 0; bridge < 2; ++bridge) {
      struct flow_offload flow = { .flags = bridge ? 1UL << NF_FLOW_BRIDGE : 0 };
      for (unsigned int value = 0; value <= 255; ++value) {
       struct iphdr ip = { .ttl = value }; struct ipv6hdr ip6 = { .hop_limit = value };
       int r4 = v4_guard(&ip, &flow), r6 = v6_guard(&ip6, &flow);
       CHECK(r4 == (value <= 1 ? -1 : 0)); CHECK(r6 == r4);
       unsigned int expected = value <= 1 || bridge ? value : value - 1;
       CHECK(ip.ttl == expected); CHECK(ip6.hop_limit == expected);
      }
     }
     struct flow_offload route = {0}, bridge = {.flags = 1UL << NF_FLOW_BRIDGE};
     struct flow_rule object = {0}; struct nf_flow_rule rule = { .rule = &object };
     CHECK(emit_keep(&route, &rule) == 0 && object.action.num_entries == 0);
     CHECK(emit_keep(&bridge, &rule) == 0 && object.action.num_entries == 1 && object.action.entries[0].id == FLOW_ACTION_KEEP_TTL);
     object.action.num_entries = 23;
     CHECK(emit_keep(&bridge, &rule) == 0 && object.action.num_entries == 24 && object.action.entries[23].id == FLOW_ACTION_KEEP_TTL);
     CHECK(emit_keep(&bridge, &rule) == -E2BIG && object.action.num_entries == 24);
     CHECK(emit_keep(&route, &rule) == 0 && object.action.num_entries == 24);
     const unsigned int types[] = { FLOW_DISSECTOR_KEY_IPV4_ADDRS, FLOW_DISSECTOR_KEY_IPV6_ADDRS, 0, FLOW_DISSECTOR_KEY_ETH_ADDRS };
     for (unsigned int i = 0; i < sizeof(types)/sizeof(types[0]); ++i) {
      for (int copies = 0; copies <= 2; ++copies) {
       uint32_t initial = 0xa5ffffffU, value = initial;
       int ret = apply_keep(types[i], copies, &value);
       bool valid = i < 2 || copies == 0;
       CHECK(ret == (valid ? 0 : -EOPNOTSUPP));
       CHECK(value == (valid && copies ? initial & ~AIROHA_FOE_IB1_BIND_TTL : initial));
      }
     }
     printf("{\\"passed\\":%u,\\"failed\\":0,\\"scope\\":\\"extracted source guards and allocation only\\"}\\n",passed);
     return 0;
    }
    '''
    with tempfile.TemporaryDirectory(prefix='bridge-ttl-') as directory:
        temporary = Path(directory)
        source = temporary / 'check.c'
        binary = temporary / 'check'
        source.write_text(code)
        compiled = subprocess.run(
            compiler + ['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
                        str(source), '-o', str(binary)],
            capture_output=True, text=True, timeout=60)
        if compiled.returncode:
            raise AssertionError('host C compile: ' + compiled.stderr.strip()[:2000])
        check('extracted C compiles', True)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise AssertionError('extracted C checks: ' + result.stderr.strip()[:2000])
        check('extracted C matrix passes', True)
        return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Prepared kernel source directory')
    args = parser.parse_args()
    checks = []
    try:
        compiler = shlex.split(os.environ.get('CC', 'cc'))
        if not compiler:
            raise ValueError('CC must name a host C compiler')
        matrix = run_checks(args.source.resolve(), compiler, checks)
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'FAIL', 'structural_passed': len(checks),
                          'failed': 1, 'error': str(error), 'limitations': LIMITATIONS}))
        return 1
    print(json.dumps({'status': 'PASS', 'structural_passed': len(checks),
                      'extracted_c': matrix, 'limitations': LIMITATIONS}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
