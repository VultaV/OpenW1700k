'use strict';
// Optional integration test using linkedom (install separately or set NODE_PATH).
// Usage: node tests/test_wireless_form_runtime.js NETWORK_JS WIRELESS_JS CAPTURE_DIR
//        [normalized|guard] [RUNTIME_CHECK_JS]
// CAPTURE_DIR supplies the captured minified luci.js and complete form.js.
// The real form/network/wireless render and poll methods run against a DOM;
// RPC/UCI/UI host dependencies are fakes, so this is not a live-router test.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {parseHTML, DOMParser} = require('linkedom');
const [networkFile, wirelessFile, captureDir, expected = 'normalized', runtimeCheckFile] = process.argv.slice(2);
assert(networkFile && wirelessFile && captureDir,
    'Pass network.js, wireless.js and the directory containing captured luci.js/form.js');
assert(['normalized', 'guard'].includes(expected));
const fixtureDir = path.join(__dirname, 'fixtures/wireless-runtime');
const config = JSON.parse(fs.readFileSync(path.join(fixtureDir, 'uci-wireless.json')));
const radios = JSON.parse(fs.readFileSync(path.join(fixtureDir, 'getWirelessDevices.json')));
const {document, window} = parseHTML('<html><body><div id="view"></div></body></html>');
const uci = {
    get: (pkg, sid, option) => pkg !== 'wireless' ? null
        : option == null ? config[sid] : config[sid]?.[option],
    sections(pkg, type, callback) {
        const sections = pkg === 'wireless'
            ? Object.values(config).filter(s => !type || s['.type'] === type) : [];
        if (callback) sections.forEach(callback);
        return sections;
    },
    load: async () => {}, loadPackage: async () => {}, changes: async () => ({})
};
const assocDevices = [];
const rpc = {
    declare: spec => async (...args) => {
        if (spec.method === 'getWirelessDevices') return radios;
        if (spec.method === 'assoclist') assocDevices.push(args[0]);
        return spec.method === 'dump' ? [] : Object.values(spec.expect || {'': {}})[0];
    },
    list: async () => ({})
};
const L = {
    toArray: v => v == null ? [] : Array.isArray(v) ? v : typeof v === 'object' ? [v]
        : String(v).trim() === '' ? [] : String(v).trim().split(/\s+/),
    naturalCompare: new Intl.Collator(undefined, {numeric: true}).compare,
    bind: (fn, self, ...args) => fn.bind(self, ...args),
    isObject: v => v !== null && typeof v === 'object',
    isArguments: v => Object.prototype.toString.call(v) === '[object Arguments]',
    hasSystemFeature: () => true, hasViewPermission: () => true,
    resolveDefault: (value, fallback) => Promise.resolve(value).catch(() => fallback),
    error: (type, message) => { throw new Error(type + ': ' + message); },
    resource: p => p, url: p => p,
    itemlist(node, items) {
        for (let i = 0; i < items.length; i += 2) {
            if (items[i + 1] == null) continue;
            node.appendChild(document.createTextNode(items[i] + ' '));
            const value = items[i + 1];
            node.appendChild(value?.nodeType ? value : document.createTextNode(String(value)));
        }
        return node;
    }
};
const polls = [];
const env = {Promise, Intl, document, window, DOMParser, uci, rpc, L, setTimeout, clearTimeout,
    LuCI: {prototype: L}, firewall: {getZones: async () => []}, validation: {},
    poll: {add: fn => polls.push(fn)}, fs: {}, uqr: {}, widgets: {},
    ui: {changes: {changes: {}}, createHandlerFn: () => () => {},
        tabs: {updateTabs() {}, initTabGroup() {}}},
    _: text => text, N_: text => text, cbi_update_table() {}};
const context = vm.createContext(env);
vm.runInContext("String.prototype.format = function(...args) { let i = 0; return this.replace(/%(?:\\.\\d+)?[sdfhq]/g, () => String(args[i++])); };", context);
const luci = fs.readFileSync(path.join(captureDir, 'luci.js'), 'utf8');
const classStart = luci.indexOf('const toCamelCase=');
const classEnd = luci.indexOf('const Headers=');
const domStart = luci.indexOf('const DOM=');
const domEnd = luci.indexOf('const Session=');
assert(classStart >= 0 && classEnd > classStart && domStart > classEnd && domEnd > domStart,
    'Expected captured LuCI Class/DOM boundaries');
// Extract the captured Class/DOM unchanged; evaluating all of luci.js would start
// the browser loader and network requests unrelated to this read-only fixture.
vm.runInContext(luci.slice(classStart, classEnd) + '\nthis.baseclass = Class;\n' +
    'const domParser = new DOMParser();\n' + luci.slice(domStart, domEnd) +
    '\nthis.dom = DOM; this.E = DOM.create.bind(DOM);', context);
env.ui.AbstractElement = env.baseclass;
env.view = {extend: value => value};
const load = file => vm.runInContext('(function(){' + fs.readFileSync(file, 'utf8') + '\n})()', context, {filename: file});
env.form = new (load(path.join(captureDir, 'form.js')))();
env.network = new (load(networkFile))();
L.network = env.network;
L.require = async name => ({network: env.network, uci})[name];
const page = load(wirelessFile);
(async () => {
    if (runtimeCheckFile)
        await vm.runInContext(fs.readFileSync(runtimeCheckFile, 'utf8'), context, {filename: runtimeCheckFile});
    const nodes = await page.render(await page.load());
    document.querySelector('#view').appendChild(nodes);
    const rows = [...document.querySelectorAll('.cbi-section-table-row[data-sid]')]
        .map(node => node.getAttribute('data-sid'));
    assert.deepEqual(rows, ['radio0', 'default_radio0', 'radio1', 'default_radio1', 'radio2', 'default_radio2']);
    assert.match(document.querySelector('[data-sid="default_radio2"] [data-name="_stat"]').textContent,
        /Wireless is disabled/);
    assert.equal(polls.length, 1, 'Status poll registered');
    console.log('PASS actual form.js full Wireless render with all six expected rows');
    for (let i = 0; i < 3; i++) await polls[0]();
    console.log('PASS three actual Wireless status poll cycles');
    const wifi = await env.network.getWifiNetwork('default_radio2');
    assert.equal(wifi.isUp(), false);
    if (expected === 'normalized') {
        assert.equal(wifi.getID(), 'radio2.network1');
        assert.equal(wifi.getIfname(), 'radio2.network1');
        assert.equal(wifi.getDevice().device, 'radio2.network1');
        assert.equal((await env.network.getDevice('default_radio2')).device, 'radio2.network1');
        assert(assocDevices.includes('radio2.network1'));
        assert(assocDevices.every(device => typeof device === 'string'));
        console.log('PASS singleton ID, ifname, Device lookup and assoclist argument are radio2.network1');
    }
    else {
        assert.equal(wifi.getID(), undefined);
        assert.equal(wifi.getIfname(), undefined);
        assert.equal(wifi.getDevice(), null);
        assert(assocDevices.includes(undefined));
        console.log('PASS guard-only render/poll succeeds but leaves ID/ifname and assoclist argument undefined');
    }
    assert.deepEqual(config.default_radio2.device, ['radio2'], 'UCI singleton list unchanged');
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
