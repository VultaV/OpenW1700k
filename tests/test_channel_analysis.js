'use strict';
// Execute the complete pinned channel_analysis.js after applying package patches.
// Usage: node tests/test_channel_analysis.js PATH/TO/channel_analysis.js
// The fixtures retain only radio/interface topology from .device/uci-wireless.txt
// and .device/getWirelessDevices.json (2026-10-03). No identifiers or keys remain.
// RPC, network and DOM are fakes; graph layout still needs a real-browser check.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const sourceFile = process.argv[2];
assert(sourceFile, 'Pass the real channel_analysis.js with 998 + 999 applied');
const source = fs.readFileSync(sourceFile, 'utf8');
const fixtureDir = path.join(__dirname, 'fixtures', 'channel-analysis');
const originalConfig = {};
for (const line of fs.readFileSync(path.join(fixtureDir, 'uci-wireless.txt'), 'utf8').trim().split('\n')) {
    const [, sid, option, value] = line.match(/^wireless\.([^.]+)(?:\.([^=]+))?=(.*)$/);
    if (!option) originalConfig[sid] = {'.type': value};
    else {
        const values = [...value.matchAll(/'([^']*)'/g)].map(match => match[1]);
        originalConfig[sid][option] = values.length > 1 ? values : values[0];
    }
}
const originalRadios = JSON.parse(fs.readFileSync(path.join(fixtureDir, 'getWirelessDevices.json'), 'utf8'));
const notice = 'Scanning this band is not available while the radio only carries an MLO network';
const list = value => value == null ? [] : Array.isArray(value) ? value : String(value).split(/\s+/);
const clone = value => JSON.parse(JSON.stringify(value));
const walk = node => Array.isArray(node) ? node.flatMap(walk)
    : node && typeof node === 'object' ? [node, ...walk(node.children || [])] : [node];

// LuCI E() treats a scalar string child as innerHTML and array strings as text.
function E(tag, attrs, children) {
    if (typeof tag === 'string' && tag.startsWith('<svg')) return E('svg', {}, [E('g')]);
    if (attrs == null || typeof attrs !== 'object' || Array.isArray(attrs) || attrs.tag)
        [attrs, children] = [{}, attrs];
    const node = {tag, attrs: attrs || {}, children: [], style: {}, events: {}, offsetWidth: 900, offsetHeight: 400,
        appendChild(child) { this.children.push(child); return child; },
        setAttribute(name, value) { this.attrs[name] = value; },
        getAttribute(name) { return this.attrs[name]; },
        addEventListener(name, callback) { this.events[name] = callback; },
        cloneNode() { return E(this.tag, {...this.attrs}, this.children.map(child => child?.tag ? child.cloneNode(true) : child)); }};
    if (children != null) node.children = Array.isArray(children) ? children
        : children.tag ? [children] : [{html: String(children)}];
    Object.defineProperties(node, {
        childNodes: {get() { return this.children; }},
        firstElementChild: {get() { return this.children.find(child => child?.tag); }},
        lastElementChild: {get() { return this.children.filter(child => child?.tag).at(-1); }}
    });
    return node;
}

async function runtime(alter) {
    const config = clone(originalConfig), radios = clone(originalRadios);
    if (alter) alter(config, radios);
    const rpcCalls = [], polls = [], frames = [], tabNodes = [];
    const net = (sid, radioName, index) => {
        const iface = radios[radioName].interfaces.find(value => value.section === sid);
        const netid = `${radioName}.network${index + 1}`;
        return {
            get: option => config[sid][option],
            getID: () => netid,
            getIfname: () => iface?.ifname || netid,
            isDisabled: () => radios[radioName].disabled || config[sid].disabled === '1'
        };
    };
    const devices = Object.keys(radios).map(name => ({
        getName: () => name,
        get: option => config[name][option],
        getWifiNetworks: async () => Object.entries(config)
            .filter(([, section]) => section['.type'] === 'wifi-iface' && list(section.device).includes(name))
            .map(([sid], index) => net(sid, name, index))
    }));
    const rpc = {declare: spec => async device => {
        rpcCalls.push({method: spec.method, device});
        if (spec.method === 'freqlist')
            return [{band: 2, channel: 1}, {band: 5, channel: 36}, {band: 6, channel: 37}];
        if (spec.method === 'scan')
            return device === 'ap-mld0' ? [] : [{band: 2, channel: 1, signal: -45,
                quality: 60, quality_max: 70, ssid: 'Synthetic neighbor', mode: 'Master',
                bssid: '02:00:00:00:00:01'}];
        if (spec.method === 'info') return {channel: 1, bssid: '02:00:00:00:00:02'};
        throw new Error('Unexpected RPC ' + spec.method);
    }};
    const env = {
        E, _: value => value, view: {extend: proto => proto}, rpc,
        network: {getWifiDevices: async () => devices},
        request: {get: async () => ({ok: true, text: () => '<svg><g/></svg>'})},
        requestAnimationFrame: callback => frames.push(callback),
        random: {derive_color: () => '#123456'},
        L: {resource: value => value, bind: (fn, self, ...args) => fn.bind(self, ...args), toArray: list},
        poll: {add: callback => polls.push(callback), start() {}, stop() {}},
        ui: {createHandlerFn: (self, method) => self[method].bind(self),
            tabs: {initTabGroup(nodes) { tabNodes.push(...nodes); }}},
        document: {createElementNS: (ns, tag) => E(tag), createTextNode: value => String(value)},
        cbi_update_table(table, rows, placeholder) { table.rows = rows; table.placeholder = placeholder; }
    };
    const context = vm.createContext(env);
    vm.runInContext("String.prototype.format = function(...args) { let i = 0; return this.replace(/%(?:\\.\\d+)?[sdfhq]/g, () => String(args[i++])); };", context);
    const page = vm.runInContext('(function(){' + source + '\n})()', context, {filename: sourceFile});
    const root = page.render(await page.load());
    frames.forEach(callback => callback());
    const tab = id => tabNodes.find(node => node.attrs['data-tab'] === id);
    const activate = id => {
        assert(tab(id), 'Missing tab ' + id);
        assert(tab(id).events['cbi-tab-active'], 'Tab has no activation listener: ' + id);
        tab(id).events['cbi-tab-active']({detail: {tab: id}});
    };
    return {page, root, rpcCalls, polls, tabNodes, tab, activate};
}

let passed = 0, failed = 0;
async function check(name, fn) {
    try { await fn(); ++passed; console.log('PASS ' + name); }
    catch (error) { ++failed; console.error('FAIL ' + name + ': ' + error.message); }
}

(async () => {
    await check('device topology keeps all three band tabs and explains MLO-only 5/6 GHz', async () => {
        const run = await runtime();
        assert.deepEqual(run.tabNodes.map(tab => tab.attrs['data-tab']), ['radio02', 'radio15', 'radio26']);
        for (const id of ['radio15', 'radio26']) {
            assert(walk(run.tab(id)).includes(notice), id + ' is missing a text notice');
            assert(!walk(run.tab(id)).some(node => node?.html?.includes(notice)), 'notice assigned to innerHTML');
            assert(!walk(run.tab(id)).some(node => node?.tag === 'table' || node?.tag === 'svg'), 'unavailable tab contains an empty scan graph/table');
        }
    });
    await check('registered poll and manual refresh do not scan either unavailable MLO band', async () => {
        const run = await runtime();
        assert.equal(run.polls.length, 1);
        for (const id of ['radio15', 'radio26']) {
            run.activate(id);
            await run.polls[0]();
            await run.page.handleScanRefresh();
        }
        assert.deepEqual(run.rpcCalls.filter(call => call.method !== 'freqlist'), []);
    });
    await check('2.4 GHz still scans the real per-radio netdev and renders a channel 1 neighbor', async () => {
        const run = await runtime();
        run.activate('radio02');
        await run.polls[0]();
        assert.deepEqual(run.rpcCalls.filter(call => call.method !== 'freqlist'), [
            {method: 'scan', device: 'phy0.0-ap0'}, {method: 'info', device: 'phy0.0-ap0'}
        ]);
        const table = walk(run.tab('radio02')).find(node => node?.tag === 'table');
        assert.equal(table.rows.length, 1);
        assert(walk(table.rows).includes('Synthetic neighbor'));
        assert(walk(table.rows[0][2]).some(node => node === '1' || node?.html === '1'));
    });
    await check('disabled mlo=0 legacy network never becomes a scan target', async () => {
        const run = await runtime((config, radios) => {
            // Pinned network models can expose the shared MLO network on only
            // its first radio, leaving radio2 with this disabled section alone.
            config.default_radio1.device = 'radio1';
            radios.radio2.interfaces = [{section: 'default_radio2', ifname: 'phy0.2-ap0'}];
        });
        run.activate('radio26');
        await run.polls[0]();
        assert(walk(run.tab('radio26')).includes(notice));
        assert(!run.rpcCalls.some(call => call.method === 'scan'));
    });
    await check('enabled legacy network without runtime netdev does not scan a synthetic network ID', async () => {
        const run = await runtime((config, radios) => {
            config.default_radio1.device = 'radio1';
            config.default_radio2.disabled = '0';
            radios.radio2.interfaces = [];
        });
        run.activate('radio26');
        await run.page.handleScanRefresh();
        assert(walk(run.tab('radio26')).includes(notice));
        assert(!run.rpcCalls.some(call => call.method === 'scan'));
    });
    await check('an enabled per-radio netdev is selected even when an MLO network comes first', async () => {
        const run = await runtime((config, radios) => {
            config.default_radio2.disabled = '0';
            radios.radio2.interfaces.push({section: 'default_radio2', ifname: 'phy0.2-ap0'});
        });
        run.activate('radio26');
        await run.polls[0]();
        assert(!walk(run.tab('radio26')).includes(notice));
        assert(run.rpcCalls.some(call => call.method === 'scan' && call.device === 'phy0.2-ap0'));
    });
    await check('both ap-mld0 and ap-mld-1 are rejected even with stale UCI MLO settings', async () => {
        for (const ifname of ['ap-mld0', 'ap-mld-1']) {
            const run = await runtime((config, radios) => {
                config.default_radio1.device = 'radio1';
                config.default_radio1.mlo = '0';
                radios.radio1.interfaces[0].ifname = ifname;
            });
            run.activate('radio15');
            await run.polls[0]();
            assert(walk(run.tab('radio15')).includes(notice), 'Missing notice for ' + ifname);
            assert(!run.rpcCalls.some(call => call.method === 'scan'));
        }
    });
    await check('explicit mlo=0 multi-radio sections retain their real per-radio scan netdevs', async () => {
        const run = await runtime((config, radios) => {
            config.default_radio1.mlo = '0';
            radios.radio1.interfaces[0].ifname = 'phy0.1-ap0';
            radios.radio2.interfaces[0].ifname = 'phy0.2-ap0';
        });
        for (const id of ['radio15', 'radio26']) {
            run.activate(id);
            await run.polls[0]();
            assert(!walk(run.tab(id)).includes(notice));
        }
        assert.deepEqual(run.rpcCalls.filter(call => call.method === 'scan').map(call => call.device),
            ['phy0.1-ap0', 'phy0.2-ap0']);
    });
    await check('radio without any network never falls back to scanning the radio name', async () => {
        const run = await runtime((config, radios) => {
            config.default_radio1.device = 'radio1';
            delete config.default_radio2;
            radios.radio2.interfaces = [];
        });
        run.activate('radio26');
        await run.polls[0]();
        assert(walk(run.tab('radio26')).includes(notice));
        assert(!run.rpcCalls.some(call => call.method === 'scan'));
    });
    await check('mlo flag identifies a custom MLD ifname with one configured radio', async () => {
        const run = await runtime((config, radios) => {
            config.default_radio1.device = 'radio1';
            radios.radio1.interfaces[0].ifname = 'custom-ap';
        });
        run.activate('radio15');
        await run.polls[0]();
        assert(walk(run.tab('radio15')).includes(notice));
        assert(!run.rpcCalls.some(call => call.method === 'scan'));
    });
    await check('multi-radio device list identifies MLO even without its flag or usual ifname', async () => {
        const run = await runtime((config, radios) => {
            delete config.default_radio1.mlo;
            radios.radio1.interfaces[0].ifname = 'custom-ap';
            radios.radio2.interfaces[0].ifname = 'custom-ap';
        });
        for (const id of ['radio15', 'radio26']) {
            run.activate(id);
            await run.polls[0]();
            assert(walk(run.tab(id)).includes(notice));
        }
        assert(!run.rpcCalls.some(call => call.method === 'scan'));
    });
    await check('returning from an unavailable tab resumes the working 2.4 GHz refresh path', async () => {
        const run = await runtime();
        run.activate('radio02');
        await run.polls[0]();
        run.activate('radio15');
        await run.polls[0]();
        run.activate('radio02');
        await run.page.handleScanRefresh();
        assert.deepEqual(run.rpcCalls.filter(call => call.method === 'scan').map(call => call.device),
            ['phy0.0-ap0', 'phy0.0-ap0']);
    });
    console.log(`${passed} PASS / ${failed} FAIL / 0 SKIP`);
    process.exitCode = failed ? 1 : 0;
})().catch(error => { console.error(error); process.exitCode = 1; });
