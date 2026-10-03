#!/usr/bin/env python3
"""Run the real github_check and github_fetch CGIs with stubbed curl, ubus and
sysupgrade. Nothing is downloaded or flashed; the scripts' /tmp paths are
redirected into a temporary directory."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CGI = ROOT/'docs/mlo-r30/overlay/www/cgi-bin'
# busybox ash is not available on the host; bash in POSIX mode stands in.
SH = [shutil.which('bash') or 'bash', '--posix']
DOWNLOAD = 'https://github.com/VultaV/OpenW1700k/releases/download/'
TAG = 'mlo-r43-20260927'
# Asset names of the published r43 release (docs/releases/mlo-r43-20260927.md).
IMAGE = ('openwrt-ubi2-mlo-npu-zero-budget-r43-20260927-tailscale-r36182-6d74443bce'
         '-airoha-an7581-gemtek_w1700k-ubi-squashfs-sysupgrade.itb')
EXTRA = ['SHA256SUMS', 'BUILD_RESULT.json', 'BUILD_WARNINGS.json',
         'SOURCE_CHANGE_PROOF.json', 'build-manifest.json',
         'GUARD_FRESH_VERIFICATION.json', 'README.md',
         'DEVICE_RESULT.json', 'DEVICE_RESULT.md']
FIRMWARE = 'offline firmware payload\n'
SHA = hashlib.sha256(FIRMWARE.encode()).hexdigest()

STUB = r'''
import json, os, pathlib, sys
base = pathlib.Path(os.environ['FIXTURE'])
name, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
with (base/'calls.jsonl').open('a') as f: f.write(json.dumps([name, args]) + '\n')
case = json.loads((base/'case.json').read_text())
if name == 'ubus':
    print(json.dumps({'access': not case.get('deny')}))
elif name == 'sysupgrade':
    sys.exit(99 if args[0] != '--test' else 1 if case.get('incompatible') else 0)
elif name == 'curl':
    api = 'https://api.github.com/repos/VultaV/OpenW1700k/releases'
    url = args[-1]
    if url == api: data = json.dumps(case['releases'])
    elif url.startswith(api + '/tags/'): data = json.dumps(case['release'])
    elif url.startswith('https://github.com/VultaV/OpenW1700k/releases/download/'):
        data = case['sums'] if url.lower().endswith('/sha256sums') else case['firmware']
    else: sys.exit(97)
    if '-o' in args: pathlib.Path(args[args.index('-o') + 1]).write_text(data)
    else: sys.stdout.write(data)
'''


def asset(name, tag=TAG):
    return {'name': name, 'browser_download_url': DOWNLOAD + tag + '/' + name}


def release():
    assets = [asset(IMAGE)] + [asset(name) for name in EXTRA]
    assets[0]['digest'] = 'sha256:' + SHA
    return {'tag_name': TAG, 'assets': assets}


class Fixture:
    def __init__(self, test, case):
        temp = tempfile.TemporaryDirectory(prefix='github-fetch-')
        test.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        bindir = self.dir/'bin'
        bindir.mkdir()
        for name in ('curl', 'ubus', 'sysupgrade'):
            (bindir/name).write_text('#!' + sys.executable + '\n' + STUB)
            (bindir/name).chmod(0o755)
        (self.dir/'case.json').write_text(json.dumps(case))
        (self.dir/'firmware.bin').write_text('previous image')
        self.env = dict(os.environ, PATH=f'{bindir}:{os.environ["PATH"]}',
                        FIXTURE=str(self.dir), REQUEST_METHOD='POST')

    def run(self, script, body=''):
        path = self.dir/script
        path.write_text((CGI/script).read_text().replace('/tmp/', f'{self.dir}/'))
        env = dict(self.env, CONTENT_LENGTH=str(len(body)))
        # Bytes, so text mode does not fold the CGI's CRLF header separator.
        out = subprocess.run(SH + [str(path)], input=body.encode(), capture_output=True,
                             env=env, timeout=30).stdout.decode()
        head, _, data = out.partition('\r\n\r\n')
        status = head[8:11] if head.startswith('Status: ') else '200'
        return status, json.loads(data)

    def calls(self, name):
        log = self.dir/'calls.jsonl'
        lines = log.read_text().splitlines() if log.exists() else []
        return [args for cmd, args in map(json.loads, lines) if cmd == name]

    def staged(self):
        assert not list(self.dir.glob('github_firmware.*')), 'staging dir left behind'
        return (self.dir/'firmware.bin').read_text()


class Fetch(unittest.TestCase):
    def fetch(self, change=None, body=None):
        case = {'release': release(), 'firmware': FIRMWARE,
                'sums': f'{SHA}  {IMAGE}\n'}
        if change:
            change(case)
        fixture = Fixture(self, case)
        request = {'tag': TAG, 'keep': True, 'sessionid': 'a' * 32}
        request.update(body or {})
        request = {k: v for k, v in request.items() if v != 'missing'}
        status, data = fixture.run('github_fetch', json.dumps(request))
        return fixture, status, data

    def test_r43_release_is_staged(self):
        fixture, status, data = self.fetch()
        self.assertEqual((status, data['sha256']), ('200', SHA), data)
        self.assertEqual(fixture.staged(), FIRMWARE)
        self.assertEqual(fixture.calls('curl')[1][-1], DOWNLOAD + TAG + '/' + IMAGE)

    def test_r43_checksum_file(self):
        def no_digest(case):
            del case['release']['assets'][0]['digest']
        fixture, status, data = self.fetch(no_digest)
        self.assertEqual((status, data['sha256']), ('200', SHA), data)
        self.assertEqual(fixture.staged(), FIRMWARE)

    def test_other_assets_rejected(self):
        def image(name):
            return lambda case: case['release']['assets'][0].update(asset(name))

        def no_digest(change=None):
            def apply(case):
                del case['release']['assets'][0]['digest']
                if change:
                    change(case)
            return apply
        board = IMAGE.replace('w1700k-ubi-', 'w1700k-')
        cases = {
            'non-UBI board': image(board),
            'other target': image(IMAGE.replace('an7581', 'en7523')),
            '.bin image': image(IMAGE.replace('.itb', '.bin')),
            'recovery image': image(IMAGE.replace('squashfs-sysupgrade', 'initramfs-recovery')),
            'two images': lambda case: case['release']['assets'].append(asset(
                IMAGE.replace('r43', 'r44'))),
            'other repository': lambda case: case['release']['assets'][0].update(
                browser_download_url='https://github.com/w1700k/builds/releases/download/x/'
                + IMAGE),
            'lowercase checksum file': no_digest(lambda case: case['release']['assets'][1].update(
                asset('sha256sums'))),
            'image missing from SHA256SUMS': no_digest(lambda case: case.update(
                sums=f'{SHA}  {board}\n')),
            'image listed twice': no_digest(lambda case: case.update(
                sums=f'{SHA}  {IMAGE}\n{"0" * 64}  {IMAGE}\n')),
        }
        for name, change in cases.items():
            with self.subTest(name):
                fixture, status, data = self.fetch(change)
                self.assertEqual(status, '502', data)
                self.assertEqual(fixture.staged(), 'previous image')
                self.assertEqual(fixture.calls('sysupgrade'), [])

    def test_checksum_mismatch_rejected(self):
        fixture, status, data = self.fetch(lambda case: case.update(firmware='tampered\n'))
        self.assertEqual(status, '422', data)
        self.assertEqual(fixture.staged(), 'previous image')
        self.assertEqual(fixture.calls('sysupgrade'), [])

    def test_keep_choice_selects_sysupgrade_test_mode(self):
        for keep, flags in ((True, ['--test']), (False, ['--test', '-n'])):
            with self.subTest(keep=keep):
                fixture, status, data = self.fetch(body={'keep': keep})
                self.assertEqual(status, '200', data)
                self.assertEqual([args[:-1] for args in fixture.calls('sysupgrade')], [flags])
                self.assertEqual(fixture.staged(), FIRMWARE)

    def test_keep_must_be_boolean(self):
        for keep in ('missing', None, 'false', 0, 1, [], {}):
            with self.subTest(keep=keep):
                fixture, status, data = self.fetch(body={'keep': keep})
                self.assertEqual(status, '400', data)
                self.assertEqual(fixture.calls('curl'), [])

    def test_failed_validation_does_not_stage(self):
        fixture, status, data = self.fetch(lambda case: case.update(incompatible=True),
                                           {'keep': False})
        self.assertEqual(status, '422', data)
        self.assertEqual(fixture.staged(), 'previous image')

    def test_session_gate(self):
        fixture, status, data = self.fetch(lambda case: case.update(deny=True))
        self.assertEqual(status, '403', data)
        self.assertEqual(fixture.calls('curl'), [])


class Check(unittest.TestCase):
    def test_lists_sysupgrade_images_only(self):
        old = 'ubi2_2026.09.07_r36111-d6f8899058'
        plain = 'openwrt-airoha-an7581-gemtek_w1700k-ubi-squashfs-sysupgrade.itb'
        r43 = release()
        r43['assets'] += [asset(IMAGE.replace('w1700k-ubi-', 'w1700k-')),
                          asset(IMAGE.replace('.itb', '.bin'))]
        fixture = Fixture(self, {'releases': [r43, {'tag_name': old,
                                                    'assets': [asset(plain, old)]}]})
        status, data = fixture.run('github_check')
        self.assertEqual(status, '200', data)
        self.assertEqual(data, [
            {'tag': TAG, 'url': DOWNLOAD + TAG + '/' + IMAGE,
             'version': 'ubi2-mlo-npu-zero-budget-r43-20260927-tailscale-r36182-6d74443bce'},
            {'tag': old, 'url': DOWNLOAD + old + '/' + plain, 'version': old}])


if __name__ == '__main__':
    unittest.main(verbosity=2)
