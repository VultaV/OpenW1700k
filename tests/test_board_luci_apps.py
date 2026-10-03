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
data=(open(args[args.index('-i')+1]).read() if '-i' in args else sys.stdin.read()) if name=='jsonfilter' else ''
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
                              text=True, env=env, cwd=self.base, timeout=20)

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


class FanControl(unittest.TestCase):
    APP = PKG/'luci-app-w1700k-fancontrol'
    INIT = APP/'root/etc/init.d/fan'
    RPC = APP/'root/usr/libexec/rpcd/luci.fan'

    def fixture(self, hwmon_name, hwmon_index, **changes):
        fx = Fixture(self, ['uci', 'jsonfilter'])
        hwmon = fx.base/'hwmon'/f'hwmon{hwmon_index}'
        hwmon.mkdir(parents=True)
        (hwmon/'name').write_text(hwmon_name + '\n')
        config = (self.APP/'root/etc/config/fan').read_text()
        for old, new in changes.items():
            old, new = f"option {old}", f"option {new}"
            self.assertIn(old, config)
            config = config.replace(old, new, 1)
        (fx.base/'config'/'fan').write_text(config)
        return fx, hwmon

    def apply_settings(self, fx):
        return fx.run(self.INIT, subs={'/sys/class/hwmon': str(fx.base/'hwmon')},
                      call='apply_settings; echo "rc=$?"')

    def test_init_skips_bad_curve_points_and_returns_to_auto(self):
        # The first point2_temp/point4_temp options belong to 'balanced'.
        fx, nct = self.fixture('nct7802', 2, **{"point2_temp '50'": "point2_temp '40.5'",
                                                "point4_temp '70'": "point4_temp '08'"})
        (nct/'pwm1_enable').write_text('2\n')
        result = self.apply_settings(fx)
        self.assertEqual((nct/'pwm1_enable').read_text(), '2\n', result.stderr)
        written = {p.name: p.read_text() for p in nct.glob('pwm1_auto_point*_temp')}
        self.assertEqual(written, {'pwm1_auto_point1_temp': '40000\n', 'pwm1_auto_point3_temp': '60000\n',
                                   'pwm1_auto_point5_temp': '80000\n'})

    def test_init_does_not_write_non_integer_manual_pwm(self):
        fx, nct = self.fixture('nct7802', 2, **{"mode 'auto'": "mode 'manual'",
                                                "manual_pwm '127'": "manual_pwm '12.5'"})
        self.apply_settings(fx)
        self.assertEqual((nct/'pwm1_enable').read_text(), '1\n')
        self.assertFalse((nct/'pwm1').exists())

    def test_init_leaves_other_hwmon5_alone_without_nct7802(self):
        fx, other = self.fixture('mt7996_phy0.1', 5)
        result = self.apply_settings(fx)
        self.assertIn('rc=1', result.stdout)
        self.assertEqual([p.name for p in other.iterdir()], ['name'])

    def test_rpc_stores_only_integer_points_in_range(self):
        fx, _ = self.fixture('nct7802', 2)
        points = [{'temp': 40.5, 'pwm': 54}, {'temp': 50, 'pwm': 69}, {'temp': 60, 'pwm': 300},
                  {'temp': '08', 'pwm': 1}, {'temp': 80, 'pwm': 255}]
        fx.run(self.RPC, ['call', 'setCustomCurve'], json.dumps({'points': points}),
               {'/sys/class/hwmon': str(fx.base/'hwmon'), '/etc/init.d/fan': 'true'})
        self.assertEqual([args[1] for args in fx.calls('uci') if args[0] == 'set'], [
            'fan.custom.point2_temp=50', 'fan.custom.point2_pwm=69',
            'fan.custom.point5_temp=80', 'fan.custom.point5_pwm=255', 'fan.settings.curve_preset=custom'])

    def test_rpc_rejects_non_integer_manual_pwm(self):
        for pwm, stored in [('12.5', None), ('08', None), ('-1', None), ('', None), ('255', '255')]:
            with self.subTest(pwm=pwm):
                fx, _ = self.fixture('nct7802', 2)
                fx.run(self.RPC, ['call', 'setManualPwm'], json.dumps({'pwm': pwm}),
                       {'/sys/class/hwmon': str(fx.base/'hwmon'), '/etc/init.d/fan': 'true'})
                sets = [args[1] for args in fx.calls('uci') if args[0] == 'set']
                self.assertEqual(sets, [f'fan.settings.manual_pwm={stored}'] if stored else [])

    def test_rpc_status_keeps_uci_strings_in_their_own_fields(self):
        # The ACL grants "uci": ["fan"] write, so a delegate can store a quote here
        forged = 'x","fan_mode_desc":"<img src=x onerror=alert(1)>","y":"'
        fx, _ = self.fixture('nct7802', 2, **{"mode 'auto'": f"mode '{forged}'",
                                                "curve_preset 'balanced'": f"curve_preset '{forged}'"})
        result = fx.run(self.RPC, ['call', 'getStatus'], subs={'/sys/class/hwmon': str(fx.base/'hwmon')})
        status = json.loads(result.stdout)
        self.assertEqual([status['fan_mode_desc'], status['uci_mode'], status['uci_preset']],
                         ['Full Speed', 'auto', 'balanced'])

    def test_rpc_curves_report_only_integer_points(self):
        # Curve points are printed into JSON unquoted. A quote can close the
        # quiet array and replace it, a non-integer or zero-padded one leaves
        # invalid JSON.
        forged = '255}],"quiet":"<img src=x onerror=alert(1)>","z":[{"a":0'
        for value in [forged, 'abc', '', '08']:
            with self.subTest(value=value):
                # The first point5_temp '85' and point5_pwm '255' belong to 'quiet'
                fx, _ = self.fixture('nct7802', 2, **{"point5_temp '85'": f"point5_temp '{value}'",
                                                        "point5_pwm '255'": f"point5_pwm '{value}'"})
                curves = json.loads(fx.run(self.RPC, ['call', 'getAllCurves']).stdout)
                self.assertEqual(list(curves), ['quiet', 'balanced', 'performance', 'custom'])
                self.assertEqual(curves['quiet'][3:], [{'temp': 75, 'pwm': 199}, {'temp': 0, 'pwm': 0}])
                self.assertEqual(curves['balanced'][4], {'temp': 80, 'pwm': 255})
                result = fx.run(self.RPC, ['call', 'getCurve'], json.dumps({'preset': 'quiet'}))
                self.assertEqual(json.loads(result.stdout)['points'][4], {'temp': 0, 'pwm': 0})

    def test_ui_accepts_only_integers(self):
        view = (self.APP/'htdocs/luci-static/resources/view/fan/settings.js').read_text()
        self.assertEqual(re.findall(r"datatype = '([^']+)'", view), [
            'and(uinteger,range(0,255))', 'and(uinteger,range(0,100))', 'and(uinteger,range(0,255))'])


class AirohaNpu(unittest.TestCase):
    APP = PKG/'luci-app-airoha-npu'
    RPC = APP/'root/usr/libexec/rpcd/luci.airoha_npu'

    def test_acl_does_not_expose_dev_mem(self):
        acl = json.loads((self.APP/'root/usr/share/rpcd/acl.d/luci-app-airoha-npu.json').read_text())
        for scope in acl['luci-app-airoha-npu'].values():
            if isinstance(scope, dict):
                self.assertNotIn('/dev/mem', scope.get('file', {}))

    def test_overclock_accepts_only_integer_mhz_up_to_stock(self):
        for freq, ok in [('abc', False), (1600, False), (1250, False), (1200.5, False), (-100, False),
                         ('0800', False), ('', False), (499, False), (500, True), (1200, True),
                         # overflows [ -lt ] / [ -gt ] in ash and bash alike
                         ('99999999999999999999', False)]:
            with self.subTest(freq=freq):
                fx = Fixture(self, ['devmem', 'jsonfilter'])
                (fx.base/'cpu/cpufreq/policy0').mkdir(parents=True)
                result = fx.run(self.RPC, ['call', 'setOverclock'], json.dumps({'freq_mhz': freq}),
                                {'. /lib/functions.sh': ':', '/sys/devices/system/cpu': str(fx.base/'cpu')})
                writes = [args for args in fx.calls('devmem') if len(args) == 3]
                if ok:
                    self.assertEqual(json.loads(result.stdout)['target_mhz'], freq)
                    self.assertTrue(writes)
                else:
                    self.assertEqual(writes, [])
                    self.assertIn('error', json.loads(result.stdout))

    def test_ui_offers_stock_maximum_only(self):
        view = (self.APP/'htdocs/luci-static/resources/view/airoha_npu/status.js').read_text()
        self.assertEqual(re.findall(r"'id':'oc-freq-input'.*'max':'(\d+)'", view), ['1200'])
        self.assertEqual(re.findall(r'isNaN\(f\)\|\|f<500\|\|f>(\d+)', view), ['1200'])


class FlowSense(unittest.TestCase):
    APP = PKG/'luci-app-airoha-flowsense'

    def test_shipped_config_pings_default_gateway(self):
        fx = Fixture(self, ['uci', 'ip'])
        shutil.copy(self.APP/'root/etc/config/npu-monitor', fx.base/'config')
        result = fx.run(self.APP/'root/etc/init.d/npu-jitter', call='start_service')
        self.assertEqual(result.stdout.split(), ['COMMAND', '/usr/libexec/npu-jitter-daemon', '192.0.2.1'])

    def daemon(self, target):
        fx = Fixture(self, ['ping', 'sleep'])
        fx.run(self.APP/'root/usr/libexec/npu-jitter-daemon', [target],
               subs={'/tmp/npu-jitter.json': str(fx.base/'npu-jitter.json')})
        return fx, (fx.base/'npu-jitter.json').read_text()

    def test_daemon_passes_target_to_awk_as_data(self):
        fx, _ = self.daemon('x", system("touch injected"), "')
        self.assertFalse((fx.base/'injected').exists())
        _, result = self.daemon('192.0.2.1')
        self.assertEqual(json.loads(result)['target'], '192.0.2.1')

    def alerts(self, last_ping):
        fx = Fixture(self, ['uci', 'jsonfilter'])
        (fx.base/'config'/'firewall').write_text("config defaults\n\toption flow_offloading_hw '1'\n")
        jitter = fx.base/'npu-jitter.json'
        jitter.write_text(json.dumps({'last_ping': last_ping}))
        result = fx.run(self.APP/'root/usr/libexec/rpcd/luci.airoha_flowsense', ['call', 'getConflictAlerts'],
                        subs={'. /lib/functions.sh': ':', '/tmp/npu-jitter.json': str(jitter)})
        return fx, result.stdout

    def test_alerts_read_last_ping_as_a_number(self):
        # The daemon prints its UCI target into the JSON unescaped, so a target
        # with quotes can append a second, string last_ping
        fx, out = self.alerts('system("touch injected")+61)}#<img src=x onerror=alert(1)>')
        self.assertFalse((fx.base/'injected').exists())
        self.assertNotIn('<img', out)
        _, out = self.alerts(75.5)
        self.assertIn('high (75.5ms)', json.loads(out)['alerts'][0]['message'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
