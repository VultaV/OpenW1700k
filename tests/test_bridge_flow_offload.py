#!/usr/bin/env python3
"""Run the real shell generator against temporary sysfs/UCI/nft substitutes only."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT/'package/network/config/bridge-flow-offload'
SOURCE = PACKAGE/'files/usr/share/bridge-flow-offload/apply-rules.sh'
STUB = r'''
import fcntl,json,os,pathlib,subprocess,sys,time
base=pathlib.Path(os.environ['FIXTURE'])
name=pathlib.Path(sys.argv[0]).name
args=sys.argv[1:]
cfg=json.loads((base/'config.json').read_text())
with (base/'calls.jsonl').open('a') as f: f.write(json.dumps([name,args])+'\n')
table=base/'table.txt'
if name=='uci':
    if args==['-q','batch']:
        (base/'batch.txt').write_text(sys.stdin.read());sys.exit(0)
    key=args[-1]
    if key in cfg: print(cfg[key]);sys.exit(0)
    sys.exit(1)
if name=='uname': print(cfg.get('kernel','6.18.44-w1700k-mlo-r30'))
elif name=='logger': pass
elif name=='flock':
    if cfg.get('lock_fail'): sys.exit(1)
    fcntl.flock(int(args[-1]),fcntl.LOCK_EX)
elif name=='timeout': os.execvp(args[1],args[1:])
elif name=='bridge':
    flags=dict(isolated=False,hairpin=False,locked=False,mab=False,neigh_suppress=False,
               neigh_vlan_suppress=False,vlan_tunnel=False,learning=True,flood=True)
    flags.update(cfg.get('flags',{}))
    for field in cfg.get('missing_flags',[]): flags.pop(field,None)
    print(json.dumps([flags]))
elif name=='jsonfilter':
    value=json.load(sys.stdin)[0].get(args[-1].split('.')[-1])
    if value is not None: print(json.dumps(value) if isinstance(value,bool) else value)
elif name=='nft':
    if args==['list','tables']:
        print('table inet fw4')
        if table.exists():print('table bridge w1700k_bridge_offload')
        if cfg.get('other_table'): print(cfg['other_table'])
    elif args==['list','chains']:
        print(cfg.get('chains','table inet fw4 { chain forward { type filter hook forward priority 0; } }'))
    elif args[:3]==['list','table','bridge']:
        if not table.exists():sys.exit(1)
        print(table.read_text())
    elif args[:3]==['destroy','table','bridge']:
        assert args[3]=='w1700k_bridge_offload'
        table.unlink(missing_ok=True)
    elif '-f' in args:
        rules=pathlib.Path(args[-1]).read_text()
        assert rules.startswith('destroy table bridge w1700k_bridge_offload\n')
        assert 'table bridge w1700k_bridge_offload {' in rules
        assert 'comment "bridge-flow-offload:v1"' in rules
        if '-c' in args:
            (base/'checking').touch()
            time.sleep(cfg.get('check_delay',0))
            sys.exit(1 if cfg.get('check_fail') else 0)
        if cfg.get('apply_fail'):sys.exit(1)
        table.write_text(rules)
    else: raise AssertionError(args)
else: raise AssertionError(name)
'''


class Generator(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bridge-offline-')
        self.base = Path(self.temp.name)
        self.config = {f'bridge-flow-offload.main.{k}':v for k,v in
                       dict(enabled='1',network='lan',bridge='br-lan',ports='lan2 phy0.2-ap0').items()}
        for directory in ['sys/class/net/br-lan/bridge','sys/class/net/br-lan/brif',
                          'tmp/sysinfo','var/run','var/lock','bin','etc/hotplug.d/iface',
                          'usr/share/nftables.d/ruleset-post','proc/net/vlan','proc/sys/net/bridge']:
            (self.base/directory).mkdir(parents=True,exist_ok=True)
        (self.base/'tmp/sysinfo/board_name').write_text('gemtek,w1700k-ubi\n')
        (self.base/'sys/class/net/br-lan/bridge/vlan_filtering').write_text('0\n')
        for port in ['lan2','phy0.2-ap0']:
            p=self.base/f'sys/class/net/{port}'
            (p/'brport').mkdir(parents=True)
            (p/'brport/state').write_text('3\n')
            (p/'master').symlink_to('../br-lan')
            (self.base/f'sys/class/net/br-lan/brif/{port}').symlink_to('../../'+port)
        (self.base/'sys/class/net/phy0.2-ap0/phy80211').mkdir()
        executable=self.base/'bin/stub'
        executable.write_text('#!'+sys.executable+'\n'+STUB)
        executable.chmod(0o700)
        for name in ['uci','uname','nft','bridge','jsonfilter','timeout','flock','logger']:
            (self.base/'bin'/name).symlink_to('stub')
        script=re.sub(r'/(?:sys|tmp|var|etc|usr|proc)/',
                      lambda m:str(self.base)+m[0],SOURCE.read_text())
        self.script=self.base/'apply.sh'
        self.script.write_text(script)
        self.env=dict(os.environ,PATH=str(self.base/'bin')+':/usr/bin:/bin',FIXTURE=str(self.base))
        self.write_config()

    def tearDown(self): self.temp.cleanup()
    def write_config(self): (self.base/'config.json').write_text(json.dumps(self.config))
    def run_script(self,*args,source=False,**env):
        self.write_config()
        command=['sh','-c','config() { exit 97; }; script=$1; shift; . "$script"','sh',str(self.script)] if source else ['sh',str(self.script),*args]
        return subprocess.run(command,env=dict(self.env,**env),capture_output=True,text=True,timeout=8)
    def seed(self,owned=True):
        (self.base/'table.txt').write_text('table bridge w1700k_bridge_offload {\n comment "'+
            ('bridge-flow-offload:v1' if owned else 'unrelated')+'"\n}\n')
    def reject(self,result):
        self.assertNotEqual(result.returncode,0,result)
        self.assertFalse((self.base/'table.txt').exists(),result.stderr)
        self.assertIn('disabled:',result.stderr)

    def test_valid_direct_and_dot_source(self):
        for sourced in [False,True]:
            r=self.run_script(source=sourced)
            self.assertEqual(r.returncode,0,r.stderr)
            rules=(self.base/'table.txt').read_text()
            self.assertEqual(rules.count('ether type ip meta l4proto tcp'),2)
            self.assertNotIn('192.168.',rules)
            self.assertNotIn('5203',rules)
            self.assertNotIn('udp',rules)
            self.assertNotIn('ip6',rules)
            self.assertIn('"lan2", "phy0.2-ap0"',rules)
            self.assertFalse(list((self.base/'tmp').glob('bridge-flow-offload.*')))
        self.assertNotIn('fw4',SOURCE.read_text().split('main()')[1].replace('# No fw4 lock/command: fw4 already holds its lock when invoking script includes.',''))

    def test_hairpin_preserves_distinct_port_scope(self):
        self.config['flags']={'hairpin':True}
        result=self.run_script()
        self.assertEqual(result.returncode,0,result.stderr)
        rules=(self.base/'table.txt').read_text()
        self.assertIn('iifname "lan2" oifname "phy0.2-ap0"',rules)
        self.assertIn('iifname "phy0.2-ap0" oifname "lan2"',rules)
        self.config['missing_flags']=['hairpin']
        self.seed();self.reject(self.run_script())

    def test_disabled_clears_only_owned(self):
        self.seed();self.config['bridge-flow-offload.main.enabled']='0'
        self.assertEqual(self.run_script().returncode,0)
        self.assertFalse((self.base/'table.txt').exists())

    def test_packaged_default_is_disabled_and_preserved(self):
        config=(PACKAGE/'files/etc/config/bridge-flow-offload').read_text()
        self.assertIn("option enabled '0'",config)
        self.assertNotIn('192.168.',config)
        self.assertIn('/etc/config/bridge-flow-offload',(PACKAGE/'Makefile').read_text())

    def test_owned_name_collision_preserved(self):
        self.seed(False)
        r=self.run_script()
        self.assertNotEqual(r.returncode,0)
        self.assertIn('unrelated',(self.base/'table.txt').read_text())

    def test_invalid_inputs(self):
        for key,value in [('ports','lan2;bad phy0.2-ap0'),('ports','lan2 lan2'),
                          ('ports','lan2 phy0.2-ap0 lan4'),('ports','lan2 mystery0'),
                          ('bridge','br-lan;bad'),('enabled','yes')]:
            old=self.config['bridge-flow-offload.main.'+key]
            self.config['bridge-flow-offload.main.'+key]=value
            self.seed();self.reject(self.run_script())
            self.config['bridge-flow-offload.main.'+key]=old

    def test_missing_or_moved_port(self):
        master=self.base/'sys/class/net/phy0.2-ap0/master'
        master.unlink();self.seed();self.reject(self.run_script())
        master.symlink_to('../guest');self.seed();self.reject(self.run_script())

    def test_bridge_absent_and_port_not_forwarding(self):
        bridge=self.base/'sys/class/net/br-lan/bridge'
        bridge.rename(bridge.with_name('absent'))
        self.seed();self.reject(self.run_script())
        bridge.with_name('absent').rename(bridge)
        (self.base/'sys/class/net/lan2/brport/state').write_text('2\n')
        self.seed();self.reject(self.run_script())

    def test_unvalidated_kernel_and_legacy_bridge_netfilter(self):
        self.config['kernel']='6.18.44';self.seed();self.reject(self.run_script())
        del self.config['kernel']
        (self.base/'proc/sys/net/bridge/bridge-nf-call-iptables').write_text('1\n')
        self.seed();self.reject(self.run_script())

    def test_vlan_filtering_and_vlan_port(self):
        path=self.base/'sys/class/net/br-lan/bridge/vlan_filtering'
        path.write_text('1\n');self.seed();self.reject(self.run_script())
        path.write_text('0\n');(self.base/'proc/net/vlan/lan2').touch()
        self.seed();self.reject(self.run_script())

    def test_isolation_locked_and_unknown_flags(self):
        for flags in [{'isolated':True},{'locked':True},{'learning':False},{'backup_port':'lan4'}]:
            self.config['flags']=flags;self.seed();self.reject(self.run_script())
        self.config['flags']={};self.config['missing_flags']=['locked']
        self.seed();self.reject(self.run_script())

    def test_other_bridge_and_netdev_policy(self):
        for table in ['table bridge custom','table netdev ingress']:
            self.config['other_table']=table;self.seed();self.reject(self.run_script())

    def test_inet_ingress_policy(self):
        self.config['chains']='table inet custom { chain input { type filter hook ingress device lan2 priority -10; } }'
        self.seed();self.reject(self.run_script())

    def test_nft_check_and_apply_failure_remove_stale(self):
        for key in ['check_fail','apply_fail']:
            self.config[key]=True;self.seed();self.reject(self.run_script());del self.config[key]

    def test_legacy_migration_is_explicit(self):
        for location in ['etc/hotplug.d/iface/00-disable-bridge-flow-offload',
                         'usr/share/nftables.d/ruleset-post/30-bridge-offload.nft']:
            legacy=self.base/location;legacy.write_text('preserve me\n')
            self.seed();r=self.run_script();self.reject(r)
            self.assertIn('migration required',r.stderr)
            self.assertEqual(legacy.read_text(),'preserve me\n');legacy.unlink()

    def test_events_filter_unrelated_and_refresh_removed_name(self):
        self.seed()
        self.assertEqual(self.run_script('--net-event',ACTION='remove',DEVICENAME='unknown0').returncode,0)
        self.assertTrue((self.base/'table.txt').exists())
        (self.base/'sys/class/net/phy0.2-ap0/master').unlink()
        self.reject(self.run_script('--net-event',ACTION='remove',DEVICENAME='phy0.2-ap0'))

    def test_overlapping_final_removal_not_dropped(self):
        self.config['check_delay']=0.4;self.write_config();self.seed()
        first=subprocess.Popen(['sh',str(self.script)],env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+5
            while not (self.base/'checking').exists() and time.monotonic()<deadline:time.sleep(.01)
            self.assertTrue((self.base/'checking').exists())
            (self.base/'sys/class/net/phy0.2-ap0/master').unlink()
            last=self.run_script('--net-event',ACTION='remove',DEVICENAME='phy0.2-ap0')
            first.communicate(timeout=5)
            self.reject(last)
            self.assertNotEqual(first.returncode,0)
        finally:
            if first.poll() is None:first.terminate()
            first.communicate(timeout=5)

    def test_lock_failure_is_visible(self):
        self.config['lock_fail']=True
        r=self.run_script()
        self.assertNotEqual(r.returncode,0)
        self.assertIn('lock timed out',r.stderr)

    def test_recreate_after_external_flush(self):
        self.assertEqual(self.run_script().returncode,0)
        (self.base/'table.txt').unlink()
        self.assertEqual(self.run_script(source=True).returncode,0)
        self.assertTrue((self.base/'table.txt').exists())

    def test_include_registration_collision_and_idempotence(self):
        script=PACKAGE/'files/etc/uci-defaults/90-bridge-flow-offload'
        r=subprocess.run(['sh',str(script)],env=self.env,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        batch=(self.base/'batch.txt').read_text()
        self.assertNotIn('flow_offloading',batch)
        self.config.update({'firewall.bridge_flow_offload':'include',
            'firewall.bridge_flow_offload.path':'/usr/share/bridge-flow-offload/apply-rules.sh'})
        self.write_config()
        self.assertEqual(subprocess.run(['sh',str(script)],env=self.env,capture_output=True).returncode,0)
        self.assertEqual((self.base/'batch.txt').read_text(),batch)
        self.config['firewall.bridge_flow_offload.path']='/etc/firewall.user';self.write_config()
        self.assertNotEqual(subprocess.run(['sh',str(script)],env=self.env,capture_output=True).returncode,0)
        self.assertEqual((self.base/'batch.txt').read_text(),batch)


if __name__=='__main__':
    unittest.main(verbosity=2)
