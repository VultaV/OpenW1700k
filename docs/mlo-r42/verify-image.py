#!/usr/bin/env python3
"""Reuse the pinned r40 image verifier for the r41 -> r42 diagnostic update.

The inherited verifier retains all extraction, image, source, ABI, package,
firmware, UI, bridge and Tailscale checks. Only the explicit adaptations below
change its contract; this does not execute an image or certify device behavior.
"""
import hashlib
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / 'mlo-r40/verify-image.py'
BASE_SHA256 = '4e70456de9f8ae422cf079a670c9c31a51e5398a592eb38c66301a6e779de946'


def adapted_source():
    raw = BASE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_SHA256:
        raise AssertionError('Pinned r40 verifier changed')
    source = raw.decode()

    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise AssertionError('Expected one verifier adaptation anchor: ' + old)
        source = source.replace(old, new, 1)

    for old, new in (
        ('r40 NPU RED initialization candidate', 'r42 bounded PS trace diagnostic candidate'),
        ('R39_ARTIFACT_DIR', 'R41_ARTIFACT_DIR'),
        ('verified r39 baseline', 'verified r41 baseline'),
        ('r39 baseline manifest hash mismatch', 'r41 baseline manifest hash mismatch'),
        ('ubi2-mlo-npu-ba-r39-20260926-tailscale',
         'ubi2-mlo-link-rollback-r41-20260927-tailscale'),
        ('Wrong r39 baseline build', 'Wrong r41 baseline build'),
        ('ubi2-mlo-npu-red-r40-20260927-tailscale',
         'ubi2-mlo-ps-observe-r42-20260927-tailscale'),
        ('Wrong r40 build label', 'Wrong r42 build label'),
        ('Kernel ABI differs from r39', 'Kernel ABI differs from r41'),
        ('Module inventory differs from r39', 'Module inventory differs from r41'),
        ('kernel_payload_identical_to_r39', 'kernel_payload_identical_to_r41'),
        ('Verified r39 artifact directory', 'Verified r41 artifact directory'),
    ):
        replace(old, new)

    replace("    required_sources = {\n", """    required_sources = {
        'package/kernel/mt76/Makefile',
        'package/kernel/mt76/patches/0037-mt7996-expand-bounded-ps-transition-trace.patch',
        'package/kernel/mac80211/Makefile',
        'package/kernel/mac80211/patches/subsys/9999-rearm-station-txqs-after-link-activation-rollback.patch',
        'tests/test_mt7996_link_transition.py',
""")
    replace('PPE SRAM, mailbox or inherited TX publication patch/regression source missing from manifest',
            'PS trace, link rollback or inherited patch/regression source missing from manifest')
    replace("'6.18.44.2026.09.01~01367e60-r31', 'Wrong mt76 package version'",
            "'6.18.44.2026.09.01~01367e60-r32', 'Wrong mt76 package version'")
    replace("""        require(baseline[name]['version'].endswith('-r30') and
                packages[name]['version'] == baseline[name]['version'][:-3] + 'r31',
                f'{name}: mt76 package revision did not advance from r30 to r31')""",
            """        require(baseline[name]['version'] == '6.18.44.2026.09.01~01367e60-r31' and
                packages[name]['version'] == '6.18.44.2026.09.01~01367e60-r32',
                f'{name}: mt76 package revision did not advance from r31 to r32')""")

    # Retain the r41 mac80211 package-origin/inventory and built-payload gates.
    replace("elif key in ('P', 'V', 'D'):", "elif key in ('P', 'V', 'D', 'o'):")
    replace("                'files': files,\n",
            "                'origin': fields.get('o', ''),\n                'files': files,\n")
    replace("    allowed = {'base-files'} | mt76_packages\n", """    allowed = {'base-files'} | mt76_packages
    mac80211_packages = {name for name, item in baseline.items()
                         if item['origin'] == 'feeds/base/kernel/mac80211'}
    require(mac80211_packages == {'kmod-cfg80211', 'kmod-mac80211'},
            'Unexpected installed mac80211 source package inventory')
    for name in mac80211_packages:
        require(packages[name]['version'] == baseline[name]['version'] == '6.18.44.7.2-r3',
                f'{name}: mac80211 r3 must remain unchanged')
        require(packages[name]['origin'] == baseline[name]['origin'] and
                packages[name]['files'] == baseline[name]['files'],
                f'{name}: package origin or file inventory changed')
""")
    replace('    # Preserve the live-validated r32 forwarding/TTL implementation and guard.\n',
            """    for package, module in [('kmod-mac80211', 'mac80211.ko'),
                            ('kmod-cfg80211', 'cfg80211.ko'),
                            ('kmod-cfg80211', 'compat.ko')]:
        payloads = list(prepared.glob(
            f'mac80211-*/backports-7.2/ipkg-aarch64_cortex-a53/{package}/lib/modules/{release}/{module}'))
        require(len(payloads) == 1 and same_file(payloads[0], module_root / module),
                f'{module}: image differs from this build package payload')
    # Preserve the live-validated r32 forwarding/TTL implementation and guard.
""")
    replace('    firmware_files = inventory(firmware)\n',
            "    firmware_files = inventory(firmware)\n"
            "    require(len(firmware_files) == 11, 'Expected 11 unchanged firmware files')\n")
    return source


exec(compile(adapted_source(), str(Path(__file__).resolve()) + '::r40-adapted', 'exec'), globals())
