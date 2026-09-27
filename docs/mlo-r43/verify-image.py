#!/usr/bin/env python3
"""Reuse the pinned r42 verifier for the r42 -> r43 NPU boot guard candidate.

All existing image, ABI, package-payload, firmware, UI, bridge and Tailscale
checks remain. This does not execute firmware or establish boot/runtime safety.
"""
import hashlib
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / 'mlo-r42/verify-image.py'
BASE_SHA256 = 'a64afa365f99190924e02e468f68796a42b16d1a663be43f547ffb1f8d6a0d65'


def adapted_source():
    raw = BASE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == BASE_SHA256, 'Pinned r42 verifier changed'
    marker = 'exec(compile(adapted_source(),'
    text = raw.decode()
    assert text.count(marker) == 1
    namespace = {'__file__': str(BASE), '__name__': 'r42_verifier_definitions'}
    exec(compile(text[:text.index(marker)], str(BASE), 'exec'), namespace)
    source = namespace['adapted_source']()

    def replace(old, new):
        nonlocal source
        assert source.count(old) == 1, 'Expected one verifier adaptation anchor: ' + old
        source = source.replace(old, new, 1)

    for old, new in (
        ('r42 bounded PS trace diagnostic candidate', 'r43 NPU boot guard candidate'),
        ('R41_ARTIFACT_DIR', 'R42_ARTIFACT_DIR'),
        ('verified r41 baseline', 'verified r42 baseline'),
        ('r41 baseline manifest hash mismatch', 'r42 baseline manifest hash mismatch'),
        ('ubi2-mlo-link-rollback-r41-20260927-tailscale', 'ubi2-mlo-ps-observe-r42-20260927-tailscale'),
        ('Wrong r41 baseline build', 'Wrong r42 baseline build'),
        # Replace the candidate label via its full assertion to keep the baseline.
        ("require(manifest['build_label'] == 'ubi2-mlo-ps-observe-r42-20260927-tailscale', 'Wrong r42 build label')",
         "require(manifest['build_label'] == 'ubi2-mlo-npu-zero-budget-r43-20260927-tailscale', 'Wrong r43 build label')"),
        ('Kernel ABI differs from r41', 'Kernel ABI differs from r42'),
        ('Module inventory differs from r41', 'Module inventory differs from r42'),
        ('kernel_payload_identical_to_r41', 'kernel_payload_identical_to_r42'),
        ('Verified r41 artifact directory', 'Verified r42 artifact directory'),
    ):
        replace(old, new)
    replace('    required_sources = {\n', """    required_sources = {
        'target/linux/airoha/patches-6.18/9999-z6-net-airoha-npu-guard-zero-budget.patch',
        'package/kernel/linux/modules/netdevices.mk',
        'tests/test_airoha_npu_budget.py',
""")
    replace('PS trace, link rollback or inherited patch/regression source missing from manifest',
            'NPU boot guard or inherited patch/regression source missing from manifest')
    replace("    allowed = {'base-files'} | mt76_packages\n",
            "    allowed = {'base-files', 'kmod-airoha-npu'}\n")
    replace("    require(packages['kmod-airoha-npu']['version'] == baseline['kmod-airoha-npu']['version'] == '6.18.44-r3', 'NPU package changed')",
            "    require(baseline['kmod-airoha-npu']['version'] == '6.18.44-r3' and packages['kmod-airoha-npu']['version'] == '6.18.44-r4', 'NPU package must advance from r3 to r4')")
    replace("""        require(baseline[name]['version'] == '6.18.44.2026.09.01~01367e60-r31' and
                packages[name]['version'] == '6.18.44.2026.09.01~01367e60-r32',
                f'{name}: mt76 package revision did not advance from r31 to r32')""",
            """        require(packages[name]['version'] == baseline[name]['version'] == '6.18.44.2026.09.01~01367e60-r32',
                f'{name}: mt76 r32 must remain unchanged')""")
    replace("changed_modules == {'mt7996e.ko'}", "changed_modules == {'airoha_npu.ko'}")
    return source


exec(compile(adapted_source(), str(Path(__file__).resolve()) + '::r42-adapted', 'exec'), globals())
