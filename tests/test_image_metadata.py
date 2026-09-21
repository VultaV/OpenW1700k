#!/usr/bin/env python3
"""Exercise metadata collection with parallel make and a changed image label."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

script = Path(__file__).resolve().parents[1] / 'scripts/json_overview_image_info.py'
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root / 'target/linux').mkdir(parents=True)
    (root / 'info').mkdir()
    values = {
        'DEFAULT_PACKAGES': 'base-files busybox',
        'ARCH_PACKAGES': 'aarch64_cortex-a53',
        'LINUX_VERSION': '6.18.44',
        'LINUX_RELEASE': '1',
        'LINUX_VERMAGIC': 'test-abi',
    }
    (root / 'target/linux/Makefile').write_text('\n'.join(
        f"val.{key}:\n\t@sleep {0.2 if key == 'DEFAULT_PACKAGES' else 0}; printf '%s\\n' '{value}'"
        for key, value in values.items()
    ) + '\n')
    current = {
        'version_code': 'r1-test', 'version_number': 'repair-tailscale',
        'profiles': {'router': {'images': [{'name': 'new.itb'}]}},
    }
    (root / 'info/new.json').write_text(json.dumps(current))
    (root / 'profiles.json').write_text(json.dumps({
        'version_code': 'r1-test', 'version_number': 'old-label',
        'profiles': {'router': {'images': [{'name': 'old.itb'}]}},
    }))
    env = dict(os.environ, WORK_DIR=str(root / 'info'), MAKEFLAGS='-j8')
    subprocess.run(['python3', str(script), str(root / 'profiles.json')],
                   cwd=root, env=env, check=True)
    result = json.loads((root / 'profiles.json').read_text())
    assert result['version_number'] == 'repair-tailscale'
    assert result['profiles']['router']['images'] == [{'name': 'new.itb'}]
    assert result['default_packages'] == ['base-files', 'busybox']
    assert result['arch_packages'] == 'aarch64_cortex-a53'
    assert result['linux_kernel'] == {
        'version': '6.18.44', 'release': '1', 'vermagic': 'test-abi',
    }
print('image metadata: PASS')
