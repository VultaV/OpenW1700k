'use strict';
// Execute the complete LuCI network model and Wireless view. RPC, UCI, form
// plumbing and DOM are host fakes; this is not a real-browser test. Exercise
// every overview row and the real registered status poll, including modal status.
// Usage: node tests/test_wireless_runtime.js NETWORK_JS WIRELESS_JS [EVIDENCE_DIR|-] [MONKEYPATCH_JS]
// EVIDENCE_DIR requires typed uci-wireless.json and getWirelessDevices.json.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const [networkFile, wirelessFile, evidenceDir, monkeypatchFile] = process.argv.slice(2);
assert(networkFile && wirelessFile, 'Pass network.js and view/network/wireless.js');
const networkSource = fs.readFileSync(networkFile, 'utf8');
const wirelessSource = fs.readFileSync(wirelessFile, 'utf8');

function readEvidence(dir) {
    const typedConfig = path.join(dir, 'uci-wireless.json');
    assert(fs.existsSync(typedConfig),
        'Typed uci-wireless.json is required: uci show cannot distinguish a scalar from a one-element list');
    const config = JSON.parse(fs.readFileSync(typedConfig, 'utf8'));
    return {config, radios: JSON.parse(fs.readFileSync(path.join(dir, 'getWirelessDevices.json'), 'utf8'))};
}
const original = readEvidence(evidenceDir && evidenceDir !== '-' ? evidenceDir
    : path.join(__dirname, 'fixtures', 'wireless-runtime'));
const multi = Object.values(original.config).find(s =>
    s['.type'] === 'wifi-iface' && Array.isArray(s.device) && s.device.length > 1);
const disabled = Object.values(original.config).find(s =>
    s['.type'] === 'wifi-iface' && Array.isArray(s.device) && s.device.length === 1 && s.disabled === '1');
assert(multi && disabled && disabled.mlo === '0',
    'Fixture requires a list-device MLO section and a disabled one-element device list with mlo 0');
const mloSid = multi['.name'];
const disabledSid = disabled['.name'];
const disabledRadio = disabled.device[0];

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
        querySelector(selector) { return this.querySelectorAll(selector)[0] || null; },
        querySelectorAll(selector) { return select(this, selector); },
        setAttribute(key, value) { this.attrs[key] = value; },
        getAttribute(key) { return this.attrs[key] ?? null; },
        hasAttribute(key) { return Object.hasOwn(this.attrs, key); },
        removeAttribute(key) { delete this.attrs[key]; }};
    node.classList = {
        contains(name) { return String(node.attrs.class || '').split(/\s+/).includes(name); },
        add(name) { node.attrs.class = `${node.attrs.class || ''} ${name}`; },
        remove(name) { node.attrs.class = String(node.attrs.class || '').split(/\s+/).filter(c => c !== name).join(' '); }
    };
    if (children != null) node.children = Array.isArray(children) ? children
        : children.tag ? [children] : [{html: String(children)}];
    Object.defineProperties(node, {
        childNodes: {get() { return this.children; }},
        firstElementChild: {get() { return this.children[0]; }},
        lastElementChild: {get() { return this.children.at(-1); }}
    });
    return node;
}
const walk = node => Array.isArray(node) ? node.flatMap(walk)
    : node && typeof node === 'object' ? [node, ...walk(node.children || [])] : [];
function matches(node, selector) {
    if (!node.tag) return false;
    const tag = /^[a-z]+/.exec(selector)?.[0];
    if (tag && node.tag !== tag) return false;
    for (const [, name] of selector.matchAll(/\.([\w-]+)/g))
        if (!node.classList.contains(name)) return false;
    const id = /#([\w-]+)/.exec(selector)?.[1];
    if (id && node.attrs.id !== id) return false;
    for (const [, key, value] of selector.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g))
        if (!node.hasAttribute(key) || (value !== undefined && node.getAttribute(key) !== value)) return false;
    return true;
}
function select(node, selector) {
    const parts = selector.split(/\s+(>)\s+|\s+/).filter(Boolean);
    let nodes = [node], direct = false;
    for (const part of parts) {
        if (part === '>') { direct = true; continue; }
        nodes = nodes.flatMap(n => (direct ? n.children : walk(n.children)).filter(child => matches(child, part)));
        direct = false;
    }
    return [...new Set(nodes)];
}

function runtime(alter) {
    const {config, radios} = JSON.parse(JSON.stringify(original));
    if (alter) alter(radios, config);
    const configBefore = JSON.stringify(config);
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
    const originalUciGet = uci.get;
    const rpcCalls = [];
    const rpc = {
        declare: spec => async (...args) => {
            rpcCalls.push({method: spec.method, args});
            // A synthetic peer exercises association-table getIfname()/isUp()
            // paths; no live client identifiers are retained in the fixture.
            if (spec.method === 'assoclist' && args[0] === 'phy0.0-ap0')
                return [{mac: '02:00:00:00:00:01', signal: -50, noise: -90,
                    rx: {rate: 72000, mhz: 20}, tx: {rate: 72000, mhz: 20}}];
            return spec.method === 'getWirelessDevices' ? radios
                : spec.method === 'dump' ? [] : Object.values(spec.expect || {'': {}})[0];
        },
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
        require: async name => name === 'network' ? env.network : name === 'uci' ? uci
            : name === 'view.network.wireless' ? page : undefined,
        error: error => { throw error; },
        resource: p => p, url: p => p, itemlist(node, items) { node.items = items; return node; }
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
            this.rendered = E('div');
            for (const section of this.children) {
                await section.load();
                for (const sid of section.cfgsections()) {
                    const row = E('tr', {'class': 'cbi-section-table-row', 'data-sid': sid});
                    for (const option of section.children) {
                        if (option.textvalue)
                            row.appendChild(E('td', {'data-name': option.option}, option.textvalue(sid)));
                    }
                    row.appendChild(section.renderRowActions(sid));
                    this.rendered.appendChild(row);
                }
            }
            return this.rendered;
        }
    });
    const pollCallbacks = [];
    const modalStatus = E('span', {'class': 'ifacebadge large', 'data-network': disabledSid}, [E('small'), E('span')]);
    let root;
    const updates = [];
    function content(node, children) {
        assert(node, 'DOM update target must exist');
        updates.push(node);
        node.children = Array.isArray(children) ? children : [children];
    }
    const env = {Promise, Intl, uci, rpc, L, baseclass: Base, validation: {},
        firewall: {getZones: async () => []}, view: {extend: value => value},
        dom: {content, append: (node, child) => node.appendChild(child)},
        poll: {add(fn) { pollCallbacks.push(fn); }}, fs: {},
        ui: {changes: {changes: {}}, createHandlerFn: () => () => {}},
        form, widgets: {}, uqr: {}, E, _: text => text, N_: text => text,
        cbi_update_table(node, rows) { assert(node); node.rows = rows; },
        document: {querySelector: selector => selector.startsWith('.cbi-modal')
            ? modalStatus : root?.querySelector(selector)}};
    const context = vm.createContext(env);
    // Only presentation formatting is approximated; the two source modules are
    // evaluated completely, without extraction, rewriting or mocked methods.
    vm.runInContext("String.prototype.format = function(...args) { let i = 0; return this.replace(/%(?:\\.\\d+)?[sdfhq]/g, () => String(args[i++])); };", context);
    const load = (source, filename) => vm.runInContext('(function(){' + source + '\n})()', context, {filename});
    env.network = new (load(networkSource, networkFile))();
    L.network = env.network;
    const page = load(wirelessSource, wirelessFile);
    const ready = monkeypatchFile ? vm.runInContext(fs.readFileSync(monkeypatchFile, 'utf8'), context,
        {filename: monkeypatchFile}) : Promise.resolve();
    return {network: env.network, maps, config, rpcCalls, ready,
        async render() {
            await ready;
            root = await page.render(await page.load());
            assert.equal(pollCallbacks.length, 1, 'Overview must register its real status poll');
            return root;
        },
        async poll() {
            const before = updates.length;
            for (const callback of pollCallbacks) await callback();
            assert(updates.length > before, 'Poll must update real overview row status and badges');
            assert(modalStatus.lastElementChild.items, 'Poll must render the disabled network modal status');
            if (Object.values(radios).some(r => r.interfaces.some(i => i.ifname === 'phy0.0-ap0')))
                assert(root.querySelector('#wifi_assoclist_table').rows.length,
                    'Poll must render the synthetic associated-station row');
            assert.equal(JSON.stringify(config), configBefore, 'Rendering must not mutate UCI options');
            assert.equal(uci.get, originalUciGet, 'Runtime hooks must restore uci.get');
        }
    };
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
    await check('exact live scalar/multi-list/disabled-singleton shape renders and polls twice', async () => {
        const r = runtime();
        await r.render();
        await r.poll();
        await r.poll();
        const scalar = await r.network.getWifiNetwork('default_radio0');
        assert.equal(scalar.getID(), 'radio0.network1');
        assert.equal(scalar.getIfname(), 'phy0.0-ap0');
        const wifi = await r.network.getWifiNetwork(mloSid);
        assert.equal(wifi.getID(), undefined, 'Pinned model has no synthetic netid for a device list');
        assert.equal(wifi.getIfname(), 'ap-mld0', 'Keep the active MLO runtime name');
        assert(wifi.getDevice());
        assert(r.maps[0].children[0].cfgsections().includes(mloSid));
        assert(r.maps[0].children[0].cfgsections().includes(disabledSid));
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
        await r.poll();
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
        await r.poll();
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
        await r.poll();
        const wifi = await r.network.getWifiNetwork(mloSid);
        assert.equal(wifi.getDevice(), null);
        assert.equal(wifi.isUp(), false);
        assert(!r.maps[0].children[0].cfgsections().includes(mloSid));
    });
    await check('disabled one-element device list gets radio2.network1 and a wifi Device', async () => {
        const r = runtime();
        await r.render();
        await r.poll();
        const wifi = await r.network.getWifiNetwork(disabledSid);
        assert.equal(wifi.getID(), disabledRadio + '.network1');
        assert.equal(wifi.getIfname(), wifi.getID());
        assert.equal(wifi.getWifiDeviceName(), disabledRadio);
        assert.equal(wifi.getDevice().getType(), 'wifi');
        assert.equal(wifi.getDevice().getName(), wifi.getID());
        assert.equal(wifi.getDevice().getWifiNetwork().getID(), wifi.getID());
        assert.equal(wifi.isUp(), false);
        assert.deepEqual(r.config[disabledSid].device, [disabledRadio], 'Keep the original UCI list unchanged');
        assert.equal((await r.network.getDevice(disabledSid)).getName(), wifi.getID());
        assert(r.rpcCalls.some(call => call.method === 'assoclist' && call.args[0] === wifi.getID()),
            'Status poll must query the disabled network with its synthetic ID');
    });
    await check('disabled scalar network preserves its ID and wifi Device', async () => {
        const r = runtime((radios, config) => { config[disabledSid].device = disabledRadio; });
        await r.render();
        await r.poll();
        const wifi = await r.network.getWifiNetwork(disabledSid);
        assert.equal(wifi.getID(), disabledRadio + '.network1');
        assert.equal(wifi.getDevice().getType(), 'wifi');
        assert.equal(wifi.isUp(), false);
    });
    for (const first of ['scalar', 'list']) {
        await check(`${first}-first mixed scalar/list sections share sequential IDs and reverse lookups`, async () => {
            const r = runtime((radios, config) => {
                const sid = 'second_disabled';
                config[disabledSid].device = first === 'scalar' ? disabledRadio : [disabledRadio];
                config[sid] = {...config[disabledSid], '.name': sid,
                    device: first === 'scalar' ? [disabledRadio] : disabledRadio};
            });
            await r.render();
            await r.poll();
            for (const [i, sid] of [disabledSid, 'second_disabled'].entries()) {
                const netid = `${disabledRadio}.network${i + 1}`;
                const wifi = await r.network.getWifiNetwork(sid);
                const reverse = await r.network.getWifiNetwork(netid);
                assert.equal(wifi.getID(), netid);
                assert.equal(wifi.getDevice().getType(), 'wifi');
                assert.equal(wifi.getDevice().getName(), netid);
                assert.equal(wifi.getDevice().getWifiNetwork().getID(), netid);
                assert.equal(reverse.getName(), sid);
                assert.equal(reverse.getID(), netid);
                assert.equal((await r.network.getDevice(sid)).getName(), netid);
            }
        });
    }
    console.log(`${passed} PASS / ${failed} FAIL / 0 SKIP (typed ${evidenceDir && evidenceDir !== '-' ? 'supplied evidence' : 'sanitized live-shape fixture'}; real overview/poll methods, fake form/DOM/RPC${monkeypatchFile ? '; runtime monkeypatch' : ''})`);
    process.exitCode = failed ? 1 : 0;
})();
