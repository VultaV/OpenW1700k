'use strict';
// Execute the real WiFi 7 LuCI view with a fake DOM, the reply handling of
// LuCI rpc.js and an rpcd session built from the app's own ACL file.
// Usage: node tests/test_wifi7_ui.js [source-root]
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(process.argv[2] || path.join(__dirname, '..'));
const app = path.join(root, 'package/luci-app-wifi7');
const read = file => fs.readFileSync(path.join(app, file), 'utf8');
const code = read('htdocs/luci-static/resources/view/wifi7/index.js');
const acl = JSON.parse(read('root/usr/share/rpcd/acl.d/luci-app-wifi7.json'));
const menu = JSON.parse(read('root/usr/share/luci/menu.d/luci-app-wifi7.json'));
// A failing write may leave an unhandled promise in old code; report, do not abort.
process.on('unhandledRejection', error => console.error('note: unhandled rejection: ' + error.message));

class Text {
    constructor(text) { this.text = String(text); this.parentNode = null; }
    get textContent() { return this.text; }
}
class Element {
    constructor(tagName) {
        Object.assign(this, {tagName, attrs: {}, style: {}, children: [],
            listeners: {}, parentNode: null, disabled: false});
    }
    appendChild(child) {
        if (child.parentNode) child.parentNode.removeChild(child);
        child.parentNode = this;
        this.children.push(child);
        return child;
    }
    removeChild(child) {
        this.children.splice(this.children.indexOf(child), 1);
        child.parentNode = null;
        return child;
    }
    replaceChild(child, old) {
        if (child.parentNode) child.parentNode.removeChild(child);
        this.children[this.children.indexOf(old)] = child;
        child.parentNode = this;
        old.parentNode = null;
        return old;
    }
    get firstChild() { return this.children[0] || null; }
    get textContent() { return this.children.map(c => c.textContent).join(''); }
    set textContent(text) { this.children = []; this.appendChild(new Text(text)); }
    getAttribute(name) { return this.attrs[name]; }
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
    fire(type) { for (const fn of this.listeners[type] || []) fn({target: this}); }
    get descendants() {
        return this.children.flatMap(c => c instanceof Element ? [c, ...c.descendants] : []);
    }
    matches(sel) {
        return sel[0] === '.' ? String(this.attrs.class || '').split(' ').includes(sel.slice(1))
            : this.tagName === sel;
    }
    querySelectorAll(sel) { return this.descendants.filter(e => e.matches(sel)); }
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
    closest(sel) { let e = this; while (e && !e.matches(sel)) e = e.parentNode; return e; }
    get options() { return this.children.filter(c => c.tagName === 'option'); }
    get value() {
        if (this.tagName !== 'select') return this._value ?? '';
        const option = this.options.find(o => o.selected) || this.options[0];
        return option ? option.value : '';
    }
    set value(value) {
        if (this.tagName !== 'select') this._value = String(value);
        else this.options.forEach(o => { o.selected = o.value === String(value); });
    }
}

// LuCI E(): attributes, then children appended like dom.append(), which skips null
function makeE(byId) {
    return function E(tag, attrs, children) {
        const el = new Element(tag);
        if (attrs == null || typeof attrs !== 'object' || Array.isArray(attrs) || attrs instanceof Element)
            [attrs, children] = [{}, attrs];
        for (const [key, value] of Object.entries(attrs)) {
            if (value == null) continue;
            el.attrs[key] = value;
            if (key === 'value') el.value = value;
            if (key === 'checked') el.checked = !!value;
            if (key === 'type') el.type = value;
            if (key === 'id') byId[value] = el;
        }
        for (const child of Array.isArray(children) ? children : [children])
            if (child != null) el.appendChild(child instanceof Element ? child : new Text(child));
        return el;
    };
}

// rpc.js handleCallReply(): access errors reject; a non-zero ubus status
// rejects only with `reject: true`, otherwise it resolves through `expect`.
function makeRpc(env) {
    return {declare(spec) {
        return (...args) => new Promise((resolve, reject) => {
            const params = {};
            (spec.params || []).forEach((name, i) => { if (args[i] !== undefined) params[name] = args[i]; });
            env.calls.push({object: spec.object, method: spec.method, params});
            let reply;
            try { reply = env.ubus(spec.object, spec.method, params); }
            catch (error) { return reject(error); }
            if (spec.reject && reply[0] !== 0)
                return reject(new Error(`${spec.object}/${spec.method} failed with ubus code ${reply[0]}`));
            let ret = reply.length > 1 ? reply[1] : reply[0];
            const type = Object.prototype.toString;
            for (const key in spec.expect || {}) {
                if (ret != null && key !== '') ret = ret[key];
                if (ret == null || type.call(ret) !== type.call(spec.expect[key])) ret = spec.expect[key];
                break;
            }
            resolve(ret);
        });
    }};
}

// rpcd session: groups from luci-base.json plus the groups the menu entry
// depends on; write access to a group implies read access.
const luciBase = {
    read: {ubus: {file: ['list'], uci: ['changes', 'get']}, uci: ['system', 'luci']},
    write: {ubus: {file: ['remove'], uci: ['add', 'apply', 'confirm', 'delete', 'order', 'rename', 'set']}}
};
const glob = pattern => new RegExp('^' + pattern.replace(/[.+^${}()|\\]/g, '\\$&')
    .replace(/\*/g, '.*').replace(/\?/g, '.') + '$');
function session(level) {
    if (level === 'root') return () => true;
    const scopes = [];
    for (const group of [luciBase, ...menu['admin/network/wifi7'].depends.acl.map(name => acl[name])]) {
        if (!group) continue;
        if (group.read) scopes.push({perm: 'read', ...group.read});
        if (level === 'write' && group.write) scopes.push({perm: 'write', ...group.write});
    }
    return (scope, object, func) => scopes.some(s => scope === 'uci'
        ? (s.uci || []).includes(object) && s.perm === func
        : Object.entries(s[scope] || {}).some(([pat, funcs]) => glob(pat).test(object) && funcs.includes(func)));
}

function makeEnv(fixture, level = 'root', fail = {}) {
    const env = {calls: [], execs: [], timers: [], byId: {}, added: [],
        uci: structuredClone(fixture.uci)};
    const allow = session(level);
    env.ubus = (object, method, p) => {
        if (!allow('ubus', object, method)) throw new Error('Access denied');
        if (object === 'uci') {
            if (!allow('uci', p.config, method === 'get' ? 'read' : 'write')) return [6];
            if (fail[method] === 'deny') throw new Error('Access denied');
            if (fail[method]) return [fail[method]];
            const s = env.uci;
            switch (method) {
            case 'get': return [0, {values: structuredClone(s)}];
            case 'add': {
                const name = p.name || 'cfg0' + (env.added.length + 1) + 'f00d';
                s[name] = {'.type': p.type, ...p.values};
                env.added.push(name);
                return [0, {section: name}];
            }
            case 'set':
                if (!s[p.section]) return [4];
                Object.assign(s[p.section], p.values);
                return [0];
            case 'delete':
                if (!s[p.section]) return [4];
                delete s[p.section];
                return [0];
            case 'commit': return [0];
            }
        }
        if (object === 'luci-rpc' && method === 'getWirelessDevices')
            return [0, structuredClone(fixture.runtime)];
        if (object.startsWith('hostapd.') && fixture.hostapd[object.slice(8)])
            return [0, {status: 'ENABLED'}];
        if (object === 'file' && method === 'exec') {
            const line = [p.command, ...(p.params || [])].join(' ');
            // rpcd file.c: the command path or the whole command line needs "exec"
            if (!allow('file', p.command, 'exec') && !allow('file', line, 'exec')) return [6];
            env.execs.push(line);
            return [0, {code: 0, stdout: fixture.exec(p.command, p.params || []) || ''}];
        }
        throw new Error('Object not found');
    };
    return env;
}

function loadView(env) {
    const L = {resolveDefault: (p, d) => Promise.resolve(p).catch(() => d), bind: (fn, self) => fn.bind(self)};
    return Function('view', 'fs', 'rpc', 'poll', 'L', 'E', 'document', 'alert', 'confirm', 'setTimeout', code)(
        {extend: proto => proto}, {}, makeRpc(env), {add() {}}, L, makeE(env.byId),
        {getElementById: id => env.byId[id] || null},
        message => assert.fail('unexpected alert: ' + message), () => true,
        fn => env.timers.push(fn));
}

async function settle(env, rounds = 12) {
    for (let i = 0; i < rounds; i++) {
        for (let j = 0; j < 5; j++) await new Promise(resolve => setImmediate(resolve));
        env.timers.splice(0).forEach(fn => fn());
    }
}

const all = (node, pred) => node.descendants.filter(pred);
const button = (node, label) => all(node, e => e.tagName === 'button' && e.textContent.startsWith(label))[0];
const input = (node, placeholder) => all(node, e => e.tagName === 'input' && e.attrs.placeholder === placeholder)[0];
const sets = env => env.calls.filter(c => c.object === 'uci' && c.method === 'set').map(c => c.params);
const tabs = ['overview', 'mld', 'radio', 'legacy', 'stations', 'diagnostics'];
function clickTab(page, tab) {
    page.querySelectorAll('.wifi7-tab').find(t => t.getAttribute('data-tab') === tab).fire('click');
}
async function open(env, tab) {
    const v = loadView(env);
    const page = v.render(await v.load());
    if (tab) clickTab(page, tab);
    return {page, content: page.querySelector('.wifi7-content')};
}

const radios = Object.fromEntries(['2g', '5g', '6g'].map((band, i) =>
    ['radio' + i, {'.type': 'wifi-device', band}]));
const legacy = {'.type': 'wifi-iface', mode: 'ap', device: 'radio0', ssid: 'Legacy',
    encryption: 'psk2', key: 'legacy-passphrase'};
const mld = (ssid, extra) => ({'.type': 'wifi-iface', mode: 'ap', mlo: '1', ssid, encryption: 'sae',
    key: ssid.toLowerCase() + '-passphrase', device: ['radio1', 'radio2'], ...extra});
const stat = (channel, addr) => `state=ENABLED\nchannel=${channel}\nfreq=5000\nlink_addr=${addr}\nmld_addr[0]=${addr}\n`;
// netifd network.wireless status: section -> netdev, named by wireless.uc mlo_vif_create()
function fixture(uci, ifnames, hostapd, stations = {}) {
    const interfaces = Object.entries({default_radio0: 'phy0.0-ap0', ...ifnames})
        .map(([section, ifname]) => ({section, ifname, config: {ifname}}));
    return {uci: {...radios, default_radio0: legacy, ...uci}, hostapd,
        runtime: Object.fromEntries(Object.keys(radios).map(r => [r, {up: true, interfaces}])),
        exec: (cmd, args) => cmd === '/usr/sbin/hostapd_cli' ? (hostapd[args[1]] || [])[+args[3]]
            : cmd === '/usr/sbin/iw' ? stations[args[1]] : ''};
}
// ap_mld_1 has no ifname option, so netifd calls it ap-mld0; mlo0 sets its own ifname
const customNames = fixture({ap_mld_1: mld('Home'), mlo0: mld('Guest', {ifname: 'guest-mld'})},
    {ap_mld_1: 'ap-mld0', mlo0: 'guest-mld'},
    {'ap-mld0': [stat(6, '02:00:00:00:00:10'), stat(36, '02:00:00:00:00:11'), stat(37, '02:00:00:00:00:12')],
        'guest-mld': ['', stat(149, '02:00:00:00:00:21'), stat(101, '02:00:00:00:00:22')]},
    {'ap-mld0': 'Station aa:bb:cc:00:00:01 (on ap-mld0)\n',
        'guest-mld': 'Station aa:bb:cc:00:00:02 (on guest-mld)\n'});
// Netdev names that the old guess also gets right
const twoProfiles = fixture({mlo0: mld('First'), mlo1: mld('Second')}, {mlo0: 'ap-mld0', mlo1: 'ap-mld1'},
    {'ap-mld0': [stat(6, '02:00:00:00:00:10'), stat(36, '02:00:00:00:00:11'), stat(37, '02:00:00:00:00:12')],
        'ap-mld1': [stat(1, '02:00:00:00:00:20'), stat(149, '02:00:00:00:00:21'), stat(5, '02:00:00:00:00:22')]});

let passed = 0, failed = 0;
async function check(name, fn) {
    try { await fn(); ++passed; console.log('PASS ' + name); }
    catch (error) { ++failed; console.error('FAIL ' + name + ': ' + error.message); }
}

(async () => {
    await check('F01 ACL group is the app\'s own and the menu requires it', () => {
        assert.deepEqual(Object.keys(acl), ['luci-app-wifi7']);
        assert.deepEqual(menu['admin/network/wifi7'].depends.acl, ['luci-app-wifi7']);
    });
    await check('F01 read scope grants no command execution', () => {
        for (const group of Object.values(acl)) {
            for (const perms of Object.values(group.read.file || {})) assert(!perms.includes('exec'));
            assert(!((group.read.ubus || {}).file || []).includes('exec'));
        }
    });
    await check('F01 write session keeps the commands the editor runs', () => {
        const allow = session('write');
        assert(allow('ubus', 'file', 'exec'));
        for (const cmd of ['/sbin/wifi', '/usr/sbin/iw', '/usr/sbin/hostapd_cli']) assert(allow('file', cmd, 'exec'));
    });
    await check('F01 read-only session renders every tab, runs no command and cannot restart Wi-Fi', async () => {
        const env = makeEnv(customNames, 'read');
        const {page, content} = await open(env);
        for (const tab of tabs) clickTab(page, tab);
        assert.deepEqual(env.execs, []);
        clickTab(page, 'mld');
        button(content, 'Save & apply').fire('click');
        await settle(env);
        assert.deepEqual(env.execs, []);
    });

    const actions = {
        'MLD apply': ['mld', c => button(c, 'Save & apply').fire('click'), true],
        'radio apply': ['radio', c => button(c, 'Save & apply').fire('click'), true],
        'network save': ['legacy', c => button(c, 'Save & apply').fire('click'), true],
        'network add': ['legacy', c => {
            input(c, 'My Network').value = 'Added';
            input(c, 'min 8 characters').value = 'added-passphrase';
            button(c, 'Add network').fire('click');
        }, true],
        'network remove': ['legacy', c => button(c, 'Remove').fire('click'), true],
        'MLO toggle': ['mld', c => button(c, 'Disable MLO').fire('click'), false]
    };
    for (const [name, [tab, run, restarts]] of Object.entries(actions)) {
        for (const [what, fail] of [['write', {set: 4, add: 4, delete: 4}], ['commit', {commit: 'deny'}]]) {
            await check(`F05 ${name}: failed ${what} is reported and Wi-Fi is not restarted`, async () => {
                const env = makeEnv(twoProfiles, 'root', fail);
                const {content} = await open(env, tab);
                run(content);
                await settle(env);
                assert(!env.execs.includes('/sbin/wifi'), 'Wi-Fi restarted after a failed UCI ' + what);
                assert.match(content.textContent, /Failed/, 'failure not reported');
                assert.doesNotMatch(content.textContent, /Done/, 'success reported');
                assert(!all(content, e => e.tagName === 'button').some(b => b.disabled), 'controls left disabled');
            });
        }
        await check(`F05 ${name}: successful writes are committed${restarts ? ' before the restart' : ''}`, async () => {
            const env = makeEnv(twoProfiles);
            const {content} = await open(env, tab);
            run(content);
            await settle(env);
            const writes = env.calls.filter(c => c.object === 'uci' && c.method !== 'get');
            assert.equal(writes.at(-1).method, 'commit');
            assert.equal(env.execs.includes('/sbin/wifi'), restarts);
            assert.doesNotMatch(content.textContent, /Failed/, 'failure reported');
            if (env.added.length) assert.deepEqual(sets(env).map(s => s.section), env.added);
        });
    }

    console.log(`${passed} PASS / ${failed} FAIL / 0 SKIP`);
    process.exitCode = failed ? 1 : 0;
})().catch(error => { console.error(error); process.exitCode = 1; });
