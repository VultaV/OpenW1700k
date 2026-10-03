#!/usr/bin/env python3
"""Run the board LuCI app backends with stubbed commands, sysfs and UCI only."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT/'package'
# busybox ash is not available on the host. bash in POSIX mode shares the ash
# behaviour these checks rely on: read -t, arithmetic that evaluates a
# variable's value as an expression, and exit on an arithmetic syntax error.
SH = [shutil.which('bash') or 'bash', '--posix']
STUB = r'''
import json,os,pathlib,re,shlex,signal,sys
base=pathlib.Path(os.environ['FIXTURE'])
name=pathlib.Path(sys.argv[0]).name
args=sys.argv[1:]
data=sys.stdin.read() if name=='jsonfilter' else ''
with (base/'calls.jsonl').open('a') as f: f.write(json.dumps([name,args])+'\n')
def sections(pkg):
    path=base/'config'/pkg
    out=[]
    for line in path.read_text().splitlines() if path.exists() else []:
        t=shlex.split(line,comments=True)
        if t and t[0]=='config': out.append({'.type':t[1],'.name':t[2] if len(t)>2 else None})
        elif t and t[0]=='option': out[-1][t[1]]=t[2]
    return out
if name=='uci':
    if 'get' not in args: sys.exit(0)
    pkg,sec,opt=args[-1].split('.',2)
    m=re.fullmatch(r'@(\w+)\[(\d+)\]',sec)
    found=[s for s in sections(pkg) if (s['.type']==m[1] if m else s['.name']==sec)]
    idx=int(m[2]) if m else 0
    if len(found)>idx and opt in found[idx]: print(found[idx][opt]); sys.exit(0)
    sys.exit(1)
if name=='jsonfilter':
    try: v=json.loads(data)
    except ValueError: sys.exit(1)
    for key,idx in re.findall(r'\.(\w+)|\[(\d+)\]',args[-1][1:]):
        try: v=v[key] if key else v[int(idx)]
        except (KeyError,IndexError,TypeError): sys.exit(1)
    print(v if isinstance(v,str) else json.dumps(v))
elif name=='curl' and '--url' not in args: sys.stdout.write((base/'page.html').read_text())
elif name=='devmem' and len(args)==1: print('0x00000000')
elif name=='ip': print('default via 192.0.2.1 dev wan proto static')
elif name=='ping': print('round-trip min/avg/max = 1.234/1.234/1.234 ms')
elif name=='sleep': os.kill(os.getppid(),signal.SIGTERM)
'''


class Fixture:
    def __init__(self, test, commands):
        temp = tempfile.TemporaryDirectory(prefix='luci-apps-')
        test.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.bin = self.base/'bin'
        self.bin.mkdir()
        (self.base/'config').mkdir()
        stub = self.base/'stub.py'
        stub.write_text('#!' + sys.executable + '\n' + STUB)
        stub.chmod(0o755)
        for command in commands:
            (self.bin/command).symlink_to(stub)
        # The scripts expect GNU/busybox sed semantics such as \n in s///.
        if shutil.which('gsed'):
            (self.bin/'sed').symlink_to(shutil.which('gsed'))

    def load(self, script, subs):
        text = script.read_text()
        for old, new in subs.items():
            assert old in text, f'{old!r} not in {script}'
            text = text.replace(old, new)
        path = self.base/script.name
        path.write_text(text)
        return path

    def run(self, script, args=(), stdin='', subs={}, call=None):
        path = self.load(script, subs)
        if call is not None:
            wrapper = self.base/'wrapper.sh'
            wrapper.write_text('procd_open_instance() { :; }\n'
                               'procd_close_instance() { :; }\n'
                               'procd_set_param() { [ "$1" = command ] && shift && echo "COMMAND $*"; :; }\n'
                               f'. "{path}"\n{call}\n')
            path = wrapper
        env = dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}', FIXTURE=str(self.base))
        return subprocess.run(SH + [str(path), *args], input=stdin, capture_output=True,
                              text=True, env=env, timeout=20)

    def calls(self, name):
        log = self.base/'calls.jsonl'
        lines = log.read_text().splitlines() if log.exists() else []
        return [args for command, args in map(json.loads, lines) if command == name]


class NetSpeedTest(unittest.TestCase):
    APP = PKG/'luci-app-netspeedtest'
    RPC = APP/'root/usr/libexec/rpcd/luci.netspeedtest'
    ARCHES = ['i386', 'x86_64', 'armel', 'armhf', 'aarch64']
    URL = 'https://install.speedtest.net/app/cli/ookla-speedtest-1.2.0-linux-%s.tgz'

    def download(self, arch):
        fx = Fixture(self, ['uci', 'jsonfilter', 'curl', 'tar', 'cp', 'chmod', 'mkdir', 'rm'])
        links = ''.join(f'<a href="{self.URL % a}">{a}</a> ' for a in self.ARCHES)
        (fx.base/'page.html').write_text(f'<div>Download for Linux: {links}</div>\n')
        jshn = fx.base/'jshn.sh'
        jshn.write_text('json_init() { _json=; }\n'
                        'json_add_boolean() { _json="$_json,\\"$1\\":$([ "$2" = 1 ] && echo true || echo false)"; }\n'
                        'json_add_string() { _json="$_json,\\"$1\\":\\"$2\\""; }\n'
                        'json_dump() { echo "{${_json#,}}"; }\n')
        result = fx.run(self.RPC, ['call', 'download_ookla'], json.dumps({'arch': arch}), {
            '. /lib/functions.sh': ':',
            '/usr/share/libubox/jshn.sh': str(jshn),
            '/usr/libexec/netspeedtest/speedtest': str(fx.base/'speedtest'),
            '/tmp/': str(fx.base) + '/'})
        return fx, json.loads(result.stdout or '{}')

    def test_acl_requires_write_access_to_download_and_run(self):
        acl = json.loads((self.APP/'root/usr/share/rpcd/acl.d/luci-app-netspeedtest.json').read_text())
        acl = acl['luci-app-netspeedtest']
        self.assertEqual(acl['read']['ubus']['luci.netspeedtest'], ['ookla_verify'])
        self.assertEqual(sorted(acl['write']['ubus']['luci.netspeedtest']), ['download_ookla', 'speedtest'])

    def test_unknown_arch_is_rejected_before_any_download(self):
        for arch in ['|https://evil.invalid/pwn.tgz|p;#', 'mips', '']:
            with self.subTest(arch=arch):
                fx, reply = self.download(arch)
                self.assertEqual(fx.calls('curl'), [])
                self.assertEqual(reply, {'result': False, 'error': 'illegal arch'})

    def test_offered_arch_still_selects_its_download(self):
        fx, _ = self.download('aarch64')
        urls = [args[args.index('--url') + 1] for args in fx.calls('curl') if '--url' in args]
        self.assertEqual(urls, [self.URL % 'aarch64'])

    def test_build_does_not_empty_package_for_gitcode_remotes(self):
        self.assertNotIn('PKG_UNPACK', (self.APP/'Makefile').read_text())
        self.assertFalse((self.APP/'.prepare.sh').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
