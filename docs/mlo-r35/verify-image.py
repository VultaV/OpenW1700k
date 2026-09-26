#!/usr/bin/env python3
"""Verify the r35 link-transition repair; writes only to a new extraction directory.

Usage: verify-image.py BUILD IMAGE NEW_OUTPUT MANIFEST --baseline R34_ARTIFACT_DIR
Uses the existing fwtool/dumpimage/unsquashfs tools and verified r34 baseline.
This checks image contents, not bootability, TTL behavior, or MLO performance.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import struct
import subprocess
import zlib


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args):
    return subprocess.check_output([str(arg) for arg in args], stderr=subprocess.STDOUT)


def apk_database(path):
    packages = {}
    for block in path.read_text().split('\n\n'):
        fields, files, folder = {}, set(), ''
        for line in block.splitlines():
            if ':' not in line:
                continue
            key, value = line.split(':', 1)
            if key == 'F':
                folder = value
            elif key == 'R':
                name = Path(folder) / value
                require(not name.is_absolute() and '..' not in name.parts,
                        'Unsafe APK file path')
                files.add(name.as_posix())
            elif key in ('P', 'V', 'D'):
                fields[key] = value
        if 'P' in fields:
            require(fields['P'] not in packages, 'Duplicate installed package')
            packages[fields['P']] = {
                'version': fields['V'], 'depends': fields.get('D', '').split(),
                'files': files,
            }
    require(bool(packages), 'Empty installed APK database')
    return packages


def same_file(old, new):
    if old.is_symlink() or new.is_symlink():
        return old.is_symlink() and new.is_symlink() and os.readlink(old) == os.readlink(new)
    return old.is_file() and new.is_file() and old.read_bytes() == new.read_bytes()


def elf_header(data, label):
    require(len(data) >= 64 and data[:6] == b'\x7fELF\x02\x01',
            f'{label}: expected little-endian ELF64')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    require(header[2] == 183, f'{label}: expected AArch64')
    return header


def module_vermagic(path):
    data = path.read_bytes()
    header = elf_header(data, path.name)
    require(header[1] == 1, f'{path.name}: expected relocatable module')
    offset, size, count, names_index = header[6], header[11], header[12], header[13]
    require(size == 64 and 0 < names_index < count and offset + size * count <= len(data),
            f'{path.name}: invalid ELF section table')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, offset + i * size)
                for i in range(count)]

    def section_data(section):
        start, length = section[4:6]
        require(start + length <= len(data), f'{path.name}: truncated ELF section')
        return data[start:start + length]

    names = section_data(sections[names_index])
    info = []
    for section in sections:
        require(section[0] < len(names), f'{path.name}: invalid section name')
        name = names[section[0]:].split(b'\0', 1)[0]
        if name == b'.modinfo':
            info.extend(section_data(section).split(b'\0'))
    values = [entry[len(b'vermagic='):].decode('ascii')
              for entry in info if entry.startswith(b'vermagic=')]
    require(len(values) == 1, f'{path.name}: expected exactly one .modinfo vermagic')
    return values[0]


def verify(build, image, out, manifest_path, previous):
    manifest = json.loads(manifest_path.read_text())
    old_root = previous / 'verified-image/rootfs'
    require(image.is_file(), f'Completed image not found: {image}')
    require(not out.exists(), f'Output must be a new directory: {out}')
    manifest = json.loads(manifest_path.read_text())
    old_manifest = json.loads((previous / 'build-manifest.json').read_text())
    require(sha256(previous / 'build-manifest.json') == manifest['base_manifest_sha256'],
            'r34 baseline manifest hash mismatch')
    require(old_manifest['build_label'] == manifest['base_build'], 'Wrong baseline build')
    require(json.loads((old_root / 'etc/w1700k-mlo-repair').read_text()) == old_manifest,
            'Baseline extracted image manifest mismatch')
    require(manifest['build_profile'] == 'ubi2', 'Expected ubi2 profile')
    require(manifest['build_label'] == 'ubi2-mlo-link-transition-r35-20260926-tailscale', 'Wrong r35 build label')
    release = manifest['kernel_release']
    require(release == manifest['kernel_source'] + '-w1700k-mlo-r32', 'Wrong private release')

    profiles = json.loads((build / 'bin/targets/airoha/an7581/profiles.json').read_text())
    entries = profiles['profiles']['gemtek_w1700k-ubi']['images']
    matches = [entry for entry in entries if entry['name'] == image.name and entry['type'] == 'sysupgrade']
    require(len(matches) == 1, 'Image not uniquely listed as ubi2 sysupgrade')
    entry = matches[0]
    require(manifest['build_label'] in image.name, 'Wrong image build label')
    require(profiles['version_number'] == manifest['build_label'], 'Wrong profiles version')
    require(profiles['arch_packages'] == 'aarch64_cortex-a53', 'Wrong package architecture')
    require(profiles['git_commit'] == manifest['base_source'], 'Wrong profiles source revision')
    kernel = profiles['linux_kernel']
    require(kernel['version'] == manifest['kernel_source'], 'Wrong kernel source version')
    require(sha256(image) == entry['sha256'], 'Image SHA256 differs from profiles')
    require(kernel['vermagic'] == (build / f'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581/linux-{manifest["kernel_source"]}/.vermagic').read_text().strip(),
            'Kernel package ABI differs from prepared build')
    out.mkdir()
    run(build / 'staging_dir/host/bin/fwtool', '-i', out / 'metadata.json', image)
    metadata = json.loads((out / 'metadata.json').read_text())
    old_metadata = json.loads((previous / 'verified-image/metadata.json').read_text())
    require(str(metadata['compat_version']) == '2.0', 'Wrong ubi2 compatibility version')
    require(metadata['new_supported_devices'] == ['gemtek,w1700k-ubi'], 'Wrong supported board')
    for field, expected in {'target': 'airoha/an7581', 'board': 'gemtek_w1700k-ubi',
                            'version': manifest['build_label'],
                            'revision': old_metadata['version']['revision']}.items():
        require(metadata['version'][field] == expected, f'Wrong metadata {field}')

    dump = build / 'build_dir/host/u-boot-2026.07/tools/dumpimage'
    listing = run(dump, '-l', image).decode()
    (out / 'fit.txt').write_text(listing)
    require(re.findall(r'^ Image \d+ \(([^)]+)\)', listing, re.M) == ['kernel-1', 'fdt-1', 'rootfs-1'],
            'Unexpected FIT images/order')
    for index, (node, filename) in enumerate([
            ('kernel-1', 'kernel.gz'), ('fdt-1', 'dtb'), ('rootfs-1', 'rootfs.squashfs')]):
        run(dump, '-T', 'flat_dt', '-p', index, '-o', out / filename, image)
        section = re.split(r'\n Image \d|\n Default Configuration:', listing.split(f'({node})', 1)[1])[0]
        hashes = re.findall(r'Hash algo:\s+(\S+)\s+Hash value:\s+([0-9a-f]+)', section)
        require(bool(hashes), f'No FIT hash for {node}')
        payload = (out / filename).read_bytes()
        for algorithm, expected in hashes:
            require(algorithm in ('crc32', 'sha1', 'sha256'), f'Unsupported FIT hash {algorithm}')
            actual = (f'{zlib.crc32(payload):08x}' if algorithm == 'crc32'
                      else hashlib.new(algorithm, payload).hexdigest())
            require(actual == expected, f'{node}: {algorithm} mismatch')
    require("Default Configuration: 'config-1'" in listing and
            re.search(r'Kernel:\s+kernel-1\s+FDT:\s+fdt-1\s+Loadables:\s+rootfs-1', listing),
            'Unexpected FIT boot configuration')
    require(same_file(previous / 'verified-image/dtb', out / 'dtb'), 'DTB changed from verified ubi2')
    kernel_bytes = gzip.decompress((out / 'kernel.gz').read_bytes())
    require(('Linux version ' + release + ' ').encode() in kernel_bytes, 'New kernel release banner missing')
    require(('Linux version ' + manifest['kernel_source'] + ' ').encode() not in kernel_bytes,
            'Old kernel release banner remains')
    require(b"version magic '%s' should be '%s'" in kernel_bytes,
            'Compiled kernel vermagic rejection message missing')
    # The console device cannot be created by an unprivileged macOS verifier.
    # Extract all ordinary content, including misplaced modules/private state.
    extraction = run(build / 'staging_dir/host/bin/unsquashfs4', '-no-xattrs', '-excludes',
                     '-d', out / 'rootfs', out / 'rootfs.squashfs', 'dev/console')
    (out / 'unsquashfs.log').write_bytes(extraction)
    root = out / 'rootfs'
    release_file = (root / 'etc/openwrt_release').read_text()
    require(f"DISTRIB_RELEASE='{manifest['build_label']}'" in release_file, 'Wrong rootfs release')
    require(f"DISTRIB_REVISION='{metadata['version']['revision']}'" in release_file, 'Wrong rootfs revision')
    require(json.loads((root / 'etc/w1700k-mlo-repair').read_text()) == manifest, 'Embedded manifest mismatch')
    for name, digest in manifest['changed_source_sha256'].items():
        require(sha256(build / name) == digest, f'Changed source hash mismatch: {name}')
    for field, directory in [('inherited_mt76_patch_sha256', 'package/kernel/mt76/patches'),
                             ('inherited_hostapd_patch_sha256', 'package/network/services/hostapd/patches')]:
        for name, digest in manifest[field].items():
            require(sha256(build / directory / name) == digest, f'Inherited patch mismatch: {name}')
    for field in ('feed_patch_sha256', 'feed_recipe_overrides_sha256', 'feed_source_sha256'):
        for name, digest in manifest[field].items():
            require(sha256(build / 'feeds' / name) == digest, f'Feed source mismatch: {name}')
    steering = Path('usr/libexec/network/packet-steering.uc')
    require(same_file(root / steering, build / 'package/network/config/netifd/files' / steering),
            'Embedded packet-steering differs from source')

    packages = apk_database(root / 'lib/apk/db/installed')
    baseline = apk_database(old_root / 'lib/apk/db/installed')
    require(set(packages) == set(baseline), 'Unexpected installed package names')
    changes = {name: {'baseline': baseline[name]['version'], 'candidate': item['version']}
               for name, item in packages.items() if name in baseline and item['version'] != baseline[name]['version']}
    allowed = {'base-files'}
    mt76_packages = {name for name, item in baseline.items()
                     if '2026.09.01~01367e60-r27' in item['version']}
    allowed.update(mt76_packages)
    require(all(name in allowed for name in changes),
            f'Unexpected package version changes: {sorted(changes)}')
    require(packages['kmod-airoha-npu']['version'] == '6.18.44-r2', 'NPU package not upgraded')
    require(packages['kmod-mt7996e']['version'] == '6.18.44.2026.09.01~01367e60-r28', 'mt76 package not upgraded')
    for name in mt76_packages:
        require(packages[name]['version'] == baseline[name]['version'].replace('-r27', '-r28'),
                f'{name}: mt76 package revision not upgraded')
    require(packages['luci-app-attendedsysupgrade']['version'] == '26.250.72430~e81743d-r2', 'Updater package not upgraded')
    kernel_abi = f"{kernel['version']}~{kernel['vermagic']}-r{kernel['release']}"
    require(packages['kernel']['version'] == kernel_abi, 'Installed kernel ABI mismatch')
    require(kernel_abi == baseline['kernel']['version'], 'Kernel ABI differs from r34')
    kmods = [name for name in packages if name.startswith('kmod-')]
    for name in kmods:
        actual = [dep for dep in packages[name]['depends'] if re.match(r'^kernel(?:[=<>~]|$)', dep)]
        require(actual == ['kernel=' + kernel_abi], f'{name}: wrong exact kernel dependency')
    require({path.name for path in (root / 'lib/modules').iterdir()} == {release},
            'Old or unexpected module directory')
    module_root = root / 'lib/modules' / release
    modules = sorted(root.rglob('*.ko'))
    require(bool(modules), 'No kernel modules in image')
    module_hashes, magics = {}, set()
    for module in modules:
        require(module.parent == module_root and not module.is_symlink(), f'Misplaced module: {module.relative_to(root)}')
        magic = module_vermagic(module)
        require(magic.split()[0] == release, f'{module.name}: wrong kernel vermagic')
        magics.add(magic)
        module_hashes[module.name] = sha256(module)
    require(len(magics) == 1, 'Modules have different vermagic flags')
    require({path.name for path in (old_root / 'lib/modules' / old_manifest['kernel_release']).glob('*.ko')} == set(module_hashes),
            'Module inventory differs from r34')

    require(same_file(previous/'verified-image/kernel.gz', out/'kernel.gz'), 'Kernel payload changed')
    changed_modules = {name for name in module_hashes
                       if not same_file(old_root/'lib/modules'/release/name, module_root/name)}
    require(changed_modules == {'mt7996e.ko'},
            f'Unexpected changed modules: {sorted(changed_modules)}')
    prepared = build / 'build_dir/target-aarch64_cortex-a53_musl/linux-airoha_an7581'
    for package, module in [('kmod-airoha-npu', 'airoha_npu.ko'), ('kmod-mt7996e', 'mt7996e.ko')]:
        payloads = list(prepared.glob(f'*/ipkg-aarch64_cortex-a53/{package}/lib/modules/{release}/{module}'))
        require(len(payloads) == 1 and same_file(payloads[0], module_root / module),
                f'{module}: image differs from this build package payload')
    # Preserve the live-validated r32 forwarding/TTL implementation and guard.
    require(packages['bridge-flow-offload']['version']=='1.0-r3' and packages['ip-bridge']['version']=='6.18.0-r2', 'Wrong final package versions')
    files = build/'package/network/config/bridge-flow-offload/files'
    for source in files.rglob('*'):
        if source.is_file():
            require(same_file(source,root/source.relative_to(files)), f'Bridge package content differs: {source.name}')
    # Exercise the shipped generator with this image's kernel release.
    suite = runpy.run_path(str(build/'tests/test_bridge_flow_offload.py'))
    case = suite['Generator']()
    case.setUp.__globals__['SOURCE'] = root/'usr/share/bridge-flow-offload/apply-rules.sh'
    try:
        case.setUp()
        case.config['kernel'] = release
        result = case.run_script()
        require(result.returncode == 0, 'Image rejects its own kernel: ' + result.stderr)
    finally:
        case.tearDown()
    hook=Path('etc/hotplug.d/iface/51-bridge-flow-offload')
    require(same_file(build/'target/linux/airoha/an7581/base-files'/hook,root/hook), 'Iface hook mismatch')
    require(not (root/'etc/hotplug.d/iface/00-disable-bridge-flow-offload').exists(), 'Legacy disable hook embedded')
    require('ip-bridge' in packages['bridge-flow-offload']['depends'], 'ip-bridge dependency missing')

    firmware = root / 'lib/firmware'
    old_firmware = old_root / 'lib/firmware'
    inventory = lambda directory: {p.relative_to(directory) for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
    firmware_files = inventory(firmware)
    require(firmware_files == inventory(old_firmware), 'Firmware file names changed')
    for name in firmware_files:
        require(same_file(old_firmware / name, firmware / name), f'Firmware changed: {name}')
    firmware_packages = [name for name, item in baseline.items()
                         if any(path.startswith('lib/firmware/') for path in item['files'])]
    require(bool(firmware_packages), 'No firmware package ownership found')
    for name in firmware_packages:
        require(packages[name]['files'] == baseline[name]['files'], f'{name}: firmware package file list changed')
    preserved_packages = [name for name in baseline if name.startswith('luci-') or
                          name in ('wpad-openssl', 'hostapd-common')]
    preserved_files = set()
    changed_ui = 'www/luci-static/resources/view/attendedsysupgrade/overview.js'
    for name in preserved_packages:
        require(packages[name]['files'] == baseline[name]['files'], f'{name}: file inventory changed')
        for path in baseline[name]['files']:
            require(same_file(old_root / path, root / path), f'{name}: changed bytes/link at {path}')
            preserved_files.add(path)
    updater_check = run('node', build/'tests/test_attendedsysupgrade_images.js', root/changed_ui)
    (out/'updater-ui-check.log').write_bytes(updater_check)

    remote = manifest['remote_access']
    require(remote['private_state_embedded'] is False and remote['preserve_settings_required'] is True,
            'Unexpected Tailscale state policy')
    require(packages['tailscale']['version'] == remote['version'], 'Wrong Tailscale package version')
    require('kmod-tun' in packages and (module_root / 'tun.ko').is_file(), 'Tailscale tun module missing')
    require(os.readlink(root / 'usr/sbin/tailscale') == 'tailscaled', 'Tailscale command link wrong')
    require(os.readlink(root / 'etc/rc.d/S80tailscale') == '../init.d/tailscale', 'Tailscale boot service missing')
    daemon = root / 'usr/sbin/tailscaled'
    require(daemon.stat().st_mode & 0o111, 'Tailscale daemon not executable')
    elf_header(daemon.read_bytes(), 'tailscaled')
    for source, dest in [('tailscale.init', 'etc/init.d/tailscale'), ('tailscale.conf', 'etc/config/tailscale')]:
        require(same_file(build / 'feeds/packages/net/tailscale/files' / source, root / dest),
                f'Tailscale source mismatch: {dest}')
    require(remote['state_file'] == '/etc/tailscale/tailscaled.state', 'Unexpected Tailscale state location')
    require('/etc/tailscale/' in (root / 'lib/upgrade/keep.d/tailscale').read_text().splitlines(),
            'Tailscale state preservation missing')
    require(not list(root.rglob('tailscaled.state*')), 'Private Tailscale state embedded')
    state_dir = root / 'etc/tailscale'
    require(not state_dir.is_symlink() and (not state_dir.exists() or not any(state_dir.iterdir())),
            'Tailscale identity directory must be absent or empty')

    selected = ('airoha-eth.ko', 'airoha_npu.ko', 'nf_flow_table.ko', 'nf_flow_table_inet.ko',
                'nft_flow_offload.ko', 'nf_conntrack_bridge.ko', 'mt76.ko', 'mt76-connac-lib.ko',
                'mt7996e.ko', 'mac80211.ko', 'cfg80211.ko', 'tun.ko')
    require(set(selected) <= set(module_hashes), 'Selected diagnostic module missing')
    result = {'result': 'PASS', 'image': image.name, 'sha256': entry['sha256'],
              'kernel_release': release, 'kernel_package': kernel_abi,
              'module_vermagic': sorted(magics), 'module_count': len(modules),
              'changed_modules': sorted(changed_modules), 'kernel_payload_identical_to_r34': True,
              'kmod_package_count': len(kmods), 'package_count': len(packages),
              'firmware_files_unchanged': len(firmware_files), 'firmware_packages': sorted(firmware_packages),
              'preserved_wpad_luci_files': len(preserved_files),
              'selected_module_sha256': {name: module_hashes[name] for name in selected},
              'limits': ['Image contents only; boot, wired continuity, TTL/hop-limit and MLO remain untested.']}
    (out / 'package-changes.json').write_text(json.dumps(changes, indent=2) + '\n')
    (out / 'module-sha256.json').write_text(json.dumps(module_hashes, indent=2) + '\n')
    (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build', type=Path)
    parser.add_argument('image', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('manifest', type=Path, nargs='?', default=Path(__file__).with_name('build-manifest.json'))
    parser.add_argument('--baseline', type=Path, required=True, help='Verified r34 artifact directory, including manifest and extracted image')
    args = parser.parse_args()
    try:
        result = verify(*(path.resolve() for path in (args.build, args.image, args.output, args.manifest, args.baseline)))
    except (AssertionError, OSError, ValueError, KeyError, struct.error, subprocess.SubprocessError) as error:
        print(json.dumps({'result': 'FAIL', 'error': str(error)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
