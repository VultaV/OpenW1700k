'use strict';
// Execute the complete LuCI network model and Wireless view. RPC, UCI, form
// plumbing and DOM are inert host fakes; this is not a real-browser test.
// Usage: node tests/test_wireless_runtime.js NETWORK_JS WIRELESS_JS [EVIDENCE_DIR]
// EVIDENCE_DIR supplies uci-wireless.txt and getWirelessDevices.json unchanged.
// Without it, use the same non-identifying scalar/list/runtime data shape below.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const [networkFile, wirelessFile, evidenceDir] = process.argv.slice(2);
assert(networkFile && wirelessFile, 'Pass network.js and view/network/wireless.js');
const networkSource = fs.readFileSync(networkFile, 'utf8');
const wirelessSource = fs.readFileSync(wirelessFile, 'utf8');

function fixture() {
    const config = {};
    for (let i = 0; i < 3; i++) {
        const radio = 'radio' + i, sid = 'test_iface' + i;
        config[radio] = {'.name': radio, '.type': 'wifi-device', '.anonymous': false,
            type: 'mac80211', band: ['2g', '5g', '6g'][i], channel: '1'};
        config[sid] = {'.name': sid, '.type': 'wifi-iface', '.anonymous': false,
            device: radio, mode: 'ap', network: 'lan', ssid: 'Test', encryption: 'none'};
    }
    Object.assign(config.test_iface1, {device: ['radio1', 'radio2'], mlo: '1'});
    Object.assign(config.test_iface2, {mlo: '0', disabled: '1'});
    const iface = (section, ifname, device) => ({section, ifname,
        config: {device, network: ['lan'], mode: 'ap', ssid: 'Test'},
        iwinfo: {mode: 'Master', channel: 1, frequency: 2412}, vlans: []});
    const radios = {
        radio0: {up: true, interfaces: [iface('test_iface0', 'phy0-ap0', ['radio0'])]},
        radio1: {up: true, interfaces: [iface('test_iface1', 'ap-mld0', ['radio1', 'radio2'])]},
        radio2: {up: true, interfaces: [iface('test_iface1', 'ap-mld0', ['radio1', 'radio2'])]}
    };
    return {config, radios};
}
function readEvidence(dir) {
    const config = {};
    for (const line of fs.readFileSync(path.join(dir, 'uci-wireless.txt'), 'utf8').trim().split('\n')) {
        const m = /^wireless\.([^. =]+)(?:\.([^=]+))?=(.*)$/.exec(line);
        assert(m, 'Unsupported UCI evidence line');
        if (!m[2]) config[m[1]] = {'.name': m[1], '.type': m[3], '.anonymous': false};
        else {
            const values = [...m[3].matchAll(/'([^']*)'/g)].map(v => v[1]);
            assert(values.length, 'Expected quoted UCI option values');
            config[m[1]][m[2]] = values.length === 1 ? values[0] : values;
        }
    }
    return {config, radios: JSON.parse(fs.readFileSync(path.join(dir, 'getWirelessDevices.json'), 'utf8'))};
}
const original = evidenceDir ? readEvidence(evidenceDir) : fixture();
const multi = Object.values(original.config).find(s =>
    s['.type'] === 'wifi-iface' && Array.isArray(s.device) && s.device.length > 1);
const disabled = Object.values(original.config).find(s =>
    s['.type'] === 'wifi-iface' && typeof s.device === 'string' && s.disabled === '1');
assert(multi && disabled, 'Fixture requires a list-device MLO section and a disabled scalar-device section');
const mloSid = multi['.name'];

function Base() { if (this.__init__) this.__init__(...arguments); }
Base.extend = function(properties) {
    const Parent = this;
    function Child() { if (this.__init__) this.__init__(...arguments); }
    Child.prototype = Object.assign(Object.create(Parent.prototype), properties);
    Child.prototype.constructor = Child;
    Child.extend = Parent.extend;
    return Child;
};
// Like LuCI dom.append(), scalar string children use innerHTML; strings inside
// arrays are text. This distinction catches unsafe new notice rendering.
function E(tag, attrs, children) {
    if (Array.isArray(tag)) { children = tag; tag = '#fragment'; attrs = {}; }
    else if (attrs == null || typeof attrs !== 'object' || Array.isArray(attrs) || attrs.tag)
        [attrs, children] = [{}, attrs];
    const node = {tag, attrs: attrs || {}, children: [], style: {},
        appendChild(child) { this.children.push(child); return child; },
        prepend(child) { this.children.unshift(child); },
        querySelector() { return null; }, querySelectorAll() { return []; },
        setAttribute(key, value) { this.attrs[key] = value; },
        getAttribute(key) { return this.attrs[key] ?? null; },
        removeAttribute(key) { delete this.attrs[key]; }};
    if (children != null) node.children = Array.isArray(children) ? children
        : children.tag ? [children] : [{html: String(children)}];
    Object.defineProperties(node, {
        firstElementChild: {get() { return this.children[0]; }},
        lastElementChild: {get() { return this.children.at(-1); }}
    });
    return node;
}
const walk = node => Array.isArray(node) ? node.flatMap(walk)
    : node && typeof node === 'object' ? [node, ...walk(node.children || [])] : [];

function runtime(alter) {
    const {config, radios} = JSON.parse(JSON.stringify(original));
    if (alter) alter(radios);
    const uci = {
        get: (pkg, sid, option) => pkg !== 'wireless' ? undefined
            : option == null ? config[sid] : config[sid]?.[option],
        sections(pkg, type, callback) {
            const sections = pkg === 'wireless'
                ? Object.values(config).filter(s => !type || s['.type'] === type) : [];
            if (callback) sections.forEach(callback);
            return sections;
        },
        load: async () => {}, changes: async () => ({})
    };
    const rpc = {
        declare: spec => async () => spec.method === 'getWirelessDevices' ? radios
            : spec.method === 'dump' ? [] : Object.values(spec.expect || {'': {}})[0],
        list: async () => ({})
    };
    const L = {
        // Match the pinned luci.js, including how undefined IDs are sorted.
        toArray: v => v == null ? [] : Array.isArray(v) ? v : typeof v === 'object' ? [v]
            : String(v).trim() === '' ? [] : String(v).trim().split(/\s+/),
        naturalCompare: new Intl.Collator(undefined, {numeric: true}).compare,
        bind: (fn, self, ...args) => fn.bind(self, ...args),
        isObject: v => v !== null && typeof v === 'object',
        hasSystemFeature: () => true, hasViewPermission: () => true,
        resolveDefault: (value, fallback) => Promise.resolve(value).catch(() => fallback),
        require: async () => {}, error: error => { throw error; },
        resource: p => p, url: p => p, itemlist: node => node
    };
    const maps = [];
    const form = {Value: Base, ListValue: Base, Flag: Base, DummyValue: Base, GridSection: Base};
    form.Map = Base.extend({
        __init__() { this.children = []; maps.push(this); }, chain() {},
        section() {
            const section = {map: this, children: [], renderMoreOptionsModal() {},
                option(Type, name) {
                    const option = {section: this, option: name};
                    this.children.push(option);
                    return option;
                }};
            this.children.push(section);
            return section;
        },
        async render() {
            for (const section of this.children) {
                await section.load();
                for (const sid of section.cfgsections()) {
                    for (const option of section.children)
                        if (option.textvalue) option.textvalue(sid);
                    section.renderRowActions(sid);
                }
            }
            this.rendered = E('div');
            return this.rendered;
        }
    });
    const env = {Promise, Intl, uci, rpc, L, baseclass: Base, validation: {},
        firewall: {getZones: async () => []}, view: {extend: value => value},
        dom: {content() {}}, poll: {add() {}}, fs: {},
        ui: {changes: {changes: {}}, createHandlerFn: () => () => {}},
        form, widgets: {}, uqr: {}, E, _: text => text, N_: text => text,
        cbi_update_table() {}, document: {querySelector: () => null}};
    const context = vm.createContext(env);
    // Only presentation formatting is approximated; the two source modules are
    // evaluated completely, without extraction, rewriting or mocked methods.
    vm.runInContext("String.prototype.format = function(...args) { let i = 0; return this.replace(/%(?:\\.\\d+)?[sdfhq]/g, () => String(args[i++])); };", context);
    const load = (source, filename) => vm.runInContext('(function(){' + source + '\n})()', context, {filename});
    env.network = new (load(networkSource, networkFile))();
    L.network = env.network;
    const page = load(wirelessSource, wirelessFile);
    return {network: env.network, maps, async render() { return page.render(await page.load()); }};
}
function changeMlo(radios, fn) {
    for (const radio of Object.values(radios))
        for (const iface of radio.interfaces)
            if (iface.section === mloSid) fn(iface);
}
let passed = 0, failed = 0;
async function check(name, fn) {
    try { await fn(); ++passed; console.log('PASS ' + name); }
    catch (error) {
        ++failed;
        console.error('FAIL ' + name + ': ' + error.message);
        if (error instanceof TypeError || error.name === 'TypeError')
            console.error(error.stack.split('\n').slice(1, 6).join('\n'));
    }
}
(async () => {
    await check('unchanged active snapshot renders (reported failure is not reproduced by this snapshot)', async () => {
        const r = runtime();
        await r.render();
        const wifi = await r.network.getWifiNetwork(mloSid);
        assert.equal(wifi.getID(), undefined, 'Pinned model has no synthetic netid for a device list');
        assert.equal(typeof wifi.getIfname(), 'string', 'Snapshot supplies the active MLO ifname');
        assert(wifi.getDevice());
        assert(r.maps[0].children[0].cfgsections().includes(mloSid));
        const notices = r.maps[0].rendered.children.filter(n => n?.attrs?.class === 'alert-message notice');
        for (const notice of notices)
            assert(!walk(notice).some(n => Object.hasOwn(n, 'html')), 'Notice strings must be array children');
    });
    await check('missing top-level MLO ifname uses iwinfo.ifname', async () => {
        const r = runtime(radios => changeMlo(radios, iface => {
            iface.iwinfo = {...iface.iwinfo, ifname: iface.ifname};
            delete iface.ifname;
        }));
        await r.render();
        const wifi = await r.network.getWifiNetwork(mloSid);
        assert.equal(typeof wifi.getIfname(), 'string');
        assert(wifi.getDevice());
    });
    await check('MLO runtime entry without either ifname renders and has no device', async () => {
        const r = runtime(radios => changeMlo(radios, iface => {
            delete iface.ifname;
            if (iface.iwinfo) delete iface.iwinfo.ifname;
        }));
        await r.render();
        const wifi = await r.network.getWifiNetwork(mloSid);
        assert.equal(wifi.getIfname(), undefined);
        assert.equal(wifi.getDevice(), null);
        assert.equal(wifi.isUp(), false);
        assert(r.maps[0].children[0].cfgsections().includes(mloSid));
    });
    await check('absent MLO runtime entry has no device (existing overview omits its row)', async () => {
        const r = runtime(radios => {
            for (const radio of Object.values(radios))
                radio.interfaces = radio.interfaces.filter(iface => iface.section !== mloSid);
        });
        await r.render();
        const wifi = await r.network.getWifiNetwork(mloSid);
        assert.equal(wifi.getDevice(), null);
        assert.equal(wifi.isUp(), false);
        assert(!r.maps[0].children[0].cfgsections().includes(mloSid));
    });
    await check('disabled scalar network preserves synthetic ID and wifi device type', async () => {
        const r = runtime();
        await r.render();
        const wifi = await r.network.getWifiNetwork(disabled['.name']);
        assert.equal(wifi.getID(), disabled.device + '.network1');
        assert.equal(wifi.getIfname(), wifi.getID());
        assert.equal(wifi.getDevice().getType(), 'wifi');
        assert.equal(wifi.isUp(), false);
    });
    console.log(`${passed} PASS / ${failed} FAIL / 0 SKIP (${evidenceDir ? 'supplied evidence' : 'synthetic shape'}; browser DOM and polling not exercised)`);
    process.exitCode = failed ? 1 : 0;
})();
