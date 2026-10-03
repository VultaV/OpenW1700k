#!/usr/bin/env python3
"""Compile the W1700K sysupgrade layout helper with ASan/UBSan, run it on
synthetic FIT/DTB cases, a deterministic mutation loop and optional real
images, then run the real platform_check_image dispatch with stubs.

--libfdt is an unpacked dtc-1.8.1/libfdt (dl/dtc-1.8.1.tar.gz or
build_dir/target-*/dtc-1.8.1/libfdt). Hashes/authenticity stay with
fit_check_sign and fwtool.
"""
import argparse
import os
from pathlib import Path
import random
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
def be(*v): return struct.pack('>' + 'I' * len(v), *v)
def text(s): return s.encode() + b'\0'
def fdt(tree):
    names = bytearray(); tokens = bytearray(); offsets = {}
    def padded(b): return b + b'\0' * (-len(b) % 4)
    def node(name, body):
        tokens.extend(be(1) + padded(text(name)))
        for key, value in body.items():
            if isinstance(value, dict): continue
            if key not in offsets: offsets[key] = len(names); names.extend(text(key))
            tokens.extend(be(3, len(value), offsets[key]) + padded(value))
        for key, value in body.items():
            if isinstance(value, dict): node(key, value)
        tokens.extend(be(2))
    node('', tree); tokens.extend(be(9))
    strings = 56 + len(tokens); total = strings + len(names)
    return be(0xd00dfeed, total, 56, strings, 40, 17, 16, 0, len(names), len(tokens)) + bytes(16) + tokens + names

def partitions(dt): return dt['spi@1fa10000']['nand@0']['partitions']

def fixture(change=lambda fit, dt: None):
    dt = {'compatible': text('gemtek,w1700k-ubi'), '#address-cells': be(2), '#size-cells': be(2), 'chosen': {'rootdisk': be(10)}, 'spi@1fa10000': {'compatible': text('airoha,en7581-snand'), 'status': text('okay'), 'reg': be(0,0x1fa10000,0,0x140,0,0x1fa11000,0,0x160), 'nand@0': {'compatible': text('spi-nand'), 'reg': be(0), 'partitions': {'compatible': text('fixed-partitions'),
        '#address-cells': be(1), '#size-cells': be(1),
        'partition@700000': {'compatible': text('linux,ubi'), 'label': text('ubi'), 'reg': be(0x700000, 0x1b700000),
            'volumes': {'fit': {'volname': text('fit'), 'phandle': be(10)}}},
        'reserved_bmt@1be00000': {'label': text('reserved_bmt'), 'reg': be(0x1be00000, 0x4200000)}}}}}
    images = {}
    for name, typ, comp, pos, size in [('kernel', 'kernel', 'gzip', 4096, 16), ('fdt', 'flat_dt', 'none', 4128, len(fdt(dt))), ('rootfs', 'filesystem', 'none', 8192, 4096)]:
        images[name] = {'type': text(typ), 'arch': text('arm64'), 'compression': text(comp), 'data-position': be(pos), 'data-size': be(size)}
    images['kernel']['os'] = text('linux')
    fit = {'images': images, 'configurations': {'default': text('conf'), 'conf': {'kernel': text('kernel'), 'fdt': text('fdt'), 'loadables': text('rootfs')}}}
    original_dtb_size = images["fdt"]["data-size"]
    change(fit, dt)
    dtb = fdt(dt)
    # Preserve explicitly corrupted data-size but update a size changed only by the nested DT.
    if images['fdt']['data-size'] == original_dtb_size:
        images['fdt']['data-size'] = be(len(dtb))
    rootfs, = struct.unpack('>I', images['rootfs']['data-position'])
    result = bytearray(max(12288, rootfs + 4096)); header = fdt(fit); result[:len(header)] = header
    result[4096:4112] = bytes(16); result[4128:4128+len(dtb)] = dtb; result[rootfs:rootfs+4] = b'hsqs'
    return bytes(result)

def main():
    p = argparse.ArgumentParser(); p.add_argument('--libfdt', type=Path, required=True); p.add_argument('--image', type=Path, action='append', default=[])
    args = p.parse_args(); count = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp); exe = tmp/'check'; image = tmp/'fixture.itb'
        subprocess.run([os.environ.get('CC','clang'), '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-I'+str(args.libfdt), str(ROOT/'package/utils/w1700k-fit-check/src/w1700k-fit-check.c'), *map(str,sorted(args.libfdt.glob('*.c'))), '-o',str(exe)],check=True)
        def run(blob):
            image.write_bytes(blob); r=subprocess.run([str(exe), str(image)],capture_output=True,text=True)
            assert 'Sanitizer' not in r.stderr and 'runtime error' not in r.stderr, r.stderr
            return r
        def check(name, blob, expect=74):
            nonlocal count
            r = run(blob)
            assert r.returncode == expect, (name, r.returncode, r.stderr)
            count += 1
        check('valid UBI2', fixture(), 0)
        cases = [
            ('detached partitions', lambda f,d: d.update(partitions=d.pop('spi@1fa10000')['nand@0']['partitions'])),
            ('wrong partition compatible', lambda f,d: partitions(d).update(compatible=text('invalid'))),
            ('wrong NAND compatible', lambda f,d: d['spi@1fa10000']['nand@0'].update(compatible=text('invalid'))),
            ('wrong UBI compatible', lambda f,d: partitions(d)['partition@700000'].update(compatible=text('invalid'))),
            ('wrong NAND address', lambda f,d: d['spi@1fa10000'].update(reg=be(0,0x1fa10004,0,0x140,0,0x1fa11000,0,0x160))),
            ('inactive controller', lambda f,d: d['spi@1fa10000'].update(status=text('disabled'))),
            ('inactive NAND', lambda f,d: d['spi@1fa10000']['nand@0'].update(status=text('disabled'))),
            ('inactive UBI', lambda f,d: partitions(d)['partition@700000'].update(status=text('disabled'))),
            ('wrong board', lambda f,d: d.update(compatible=text('wrong,board'))),
            ('old UBI layout', lambda f,d: partitions(d)['partition@700000'].update(reg=be(0x700000,0x1f900000))),
            ('wrong rootdisk', lambda f,d: d['chosen'].update(rootdisk=be(999))),
            ('wrong volume', lambda f,d: partitions(d)['partition@700000']['volumes']['fit'].update(volname=text('rootfs'))),
            ('missing rootfs reference', lambda f,d: f['configurations']['conf'].pop('loadables')),
            ('recovery ramdisk', lambda f,d: f['configurations']['conf'].update(ramdisk=text('rootfs'))),
            ('bad default', lambda f,d: f['configurations'].update(default=text('missing'))),
            ('multiple configs', lambda f,d: f['configurations'].update(other={})),
            ('multiple loadables', lambda f,d: f['configurations']['conf'].update(loadables=b'rootfs\0kernel\0')),
            ('overlap', lambda f,d: f['images']['rootfs'].update(**{'data-position': be(4096)})),
            ('header overlap', lambda f,d: f['images']['kernel'].update(**{'data-position': be(8)})),
            ('out of bounds', lambda f,d: f['images']['kernel'].update(**{'data-size': be(0xffffffff)})),
            ('zero length', lambda f,d: f['images']['kernel'].update(**{'data-size': be(0)})),
            ('unaligned rootfs', lambda f,d: f['images']['rootfs'].update(**{'data-size': be(4095)})),
            ('embedded data', lambda f,d: f['images']['kernel'].update(data=b'abc')),
            ('relative payload', lambda f,d: f['images']['kernel'].update(**{'data-offset':be(0)})),
            ('wrong image type', lambda f,d: f['images']['rootfs'].update(type=text('ramdisk'))),
            ('compressed rootfs', lambda f,d: f['images']['rootfs'].update(compression=text('gzip'))),
            # A valid DTB followed by 1 MiB of padding; refused before it is copied.
            ('oversized DTB', lambda f,d: (f['images']['fdt'].update(**{'data-size': be(0x100001)}),
                                           f['images']['rootfs'].update(**{'data-position': be(0x102000)}))),
        ]
        for name, change in cases: check(name, fixture(change))
        check('truncated FIT', fixture()[:60]); check('truncated payload', fixture()[:-1]); check('not FIT', bytes(4096))
        damaged=bytearray(fixture()); damaged[8192]=0; check('bad squashfs magic',damaged)
        # Memory safety on damaged input: every result is accept or 74, never a sanitizer report.
        rng = random.Random(20261003); valid = fixture(); outcomes = {0: 0, 74: 0}
        for _ in range(400):
            blob = bytearray(valid)
            if rng.random() < 0.2:
                blob = blob[:rng.randrange(len(blob))]
            else:
                for _ in range(rng.choice((1, 2, 4, 8))):
                    blob[rng.randrange(len(blob))] = rng.choice((0, 0xff, rng.randrange(256)))
            rc = run(bytes(blob)).returncode
            assert rc in outcomes, (rc, bytes(blob))
            outcomes[rc] += 1
        assert outcomes[74], outcomes
        for real in args.image: check(f'real image {real.name}', real.read_bytes(), 0)
        # Exercise real platform dispatch without image installation or external tools.
        source=ROOT/'target/linux/airoha/an7581/base-files/lib/upgrade/platform.sh'
        stub = tmp/'w1700k-fit-check'
        for fit_rc, layout_rc in [(0,0),(74,0),(0,74),(0,None)]:
            if layout_rc is None: stub.unlink()
            else: stub.write_text(f'#!/bin/sh\nexit {layout_rc}\n'); stub.chmod(0o755)
            script=f'. "{source}"\nboard_name() {{ echo gemtek,w1700k-ubi; }}\nfit_check_image() {{ return {fit_rc}; }}\nplatform_check_image fixture\n'
            r=subprocess.run(['sh','-c',script], env=dict(os.environ, PATH=str(tmp)+':'+os.environ['PATH']), capture_output=True)
            assert r.returncode == (0 if (fit_rc, layout_rc) == (0, 0) else 74), (fit_rc, layout_rc, r.returncode)
        print(f'PASS {count} FIT layout cases, 400 mutations {outcomes} + 4 platform dispatch cases (ASan/UBSan)')
if __name__ == '__main__': main()
