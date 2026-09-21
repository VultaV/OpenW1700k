'use strict';
// Run the actual form callbacks without a router or a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const mlo = fs.readFileSync(path.join(root, 'package/luci-app-mlo/htdocs/luci-static/resources/view/mlo.js'), 'utf8');
const wifi7 = fs.readFileSync(path.join(root, 'package/luci-app-wifi7/htdocs/luci-static/resources/view/wifi7/index.js'), 'utf8');
const quickAdd = mlo.match(/quickAdd = (function\(mode\) \{[\s\S]*?\n\t\t\});/)[1];
const validate = mlo.match(/o.validate = (function\(section_id, value\) \{[\s\S]*?\n\t\t\});/)[1];

function bind(source, globals) {
    return Function(...Object.keys(globals), source)(...Object.values(globals));
}

async function checkDefaults(radios, expected) {
    const values = {};
    const create = bind('return ' + quickAdd, {
        radios, networks: [{'.name': 'lan'}], nextSectionName: () => 'mlo0',
        uci: {add() {}, set(_config, _section, key, value) { values[key] = value; }},
        s: {renderMoreOptionsModal: () => Promise.resolve()},
        ui: {addNotification() {}}, E() {}, _: text => text
    });
    await create('ap');
    assert.deepEqual(values.device, expected);
    const validation = bind('return ' + validate, {
        uniqueValues: value => [...new Set(value)], _: text => text,
        radiosByName: Object.fromEntries(radios.map(r => [r['.name'], r])),
        optionValue: () => '1'
    }).bind({section: {children: []}});
    assert.notEqual(validation('mlo0', ['radio1', 'missing']), true);
    if (expected) assert.equal(validation('mlo0', expected), true);
    const disabled = radios.find(r => r.disabled === '1');
    if (disabled) assert.notEqual(validation('mlo0', ['radio1', disabled['.name']]), true);
    const radioDefaults = wifi7.slice(wifi7.indexOf('var radioChoices ='), wifi7.indexOf('var radioChecks ='));
    const wifiDefaults = bind(radioDefaults + 'return defaultRadios;', {
        uciData: Object.fromEntries(radios.map(r => [r['.name'], {...r, '.type':'wifi-device'}]))
    });
    assert.deepEqual(wifiDefaults, expected || ['radio1']);
}

async function checkCreate(failAt) {
    const declarations = wifi7.slice(wifi7.indexOf('var callUciAddMld2 ='), wifi7.indexOf('// nextSectionName:'));
    const callback = wifi7.slice(wifi7.indexOf("doAddBtn.addEventListener('click'"), wifi7.indexOf('addForm.appendChild('));
    const calls = [];
    const key = 'Literal $HOME $(echo no) `echo no` " \\ passphrase';
    const ssid = 'MLO $HOME $(echo no)';
    const uciData = {};
    const button = {addEventListener(_event, fn) { this.click = fn; }};
    const cancel = {};
    const status = {style: {}};
    bind(declarations + callback, {
        rpc: {declare(spec) {
            return async (...args) => {
                calls.push([spec.method, args]);
                assert.equal(spec.reject, true, 'UCI errors must reject the transaction');
                if (failAt === spec.method) throw new Error(spec.method + ' failed');
                return spec.method === 'add' ? args[2] : 0;
            };
        }},
        callExec: async (command, args) => {
            calls.push(['exec', [command, args]]);
            return {code: failAt === 'reload' ? 1 : 0};
        },
        callUciGetWireless: async config => {
            calls.push(['get', [config]]);
            if (failAt === 'get') throw new Error('get failed');
            return failAt === 'exists' ? {mlo0: {ssid: 'existing'}} : {};
        },
        newSSID: {value: ssid}, newKey: {value: key}, newEncSel: {value: 'sae'},
        radioChecks: ['radio1', 'radio2'].map(radio => ({radio, chk: {checked: true}})),
        nextMloName: () => 'mlo0', doAddBtn: button, cancelAddBtn: cancel,
        addStatusSpan: status, uciData, alert: message => assert.fail(message)
    });
    await button.click();
    const expectedCalls = ['get'];
    if (failAt !== 'get' && failAt !== 'exists') {
        expectedCalls.push('add');
        if (failAt !== 'add') expectedCalls.push('commit');
        if (failAt !== 'add' && failAt !== 'commit') expectedCalls.push('exec');
    }
    assert.deepEqual(calls.map(c => c[0]), expectedCalls);
    if (calls[1]) assert.deepEqual(calls[1][1], ['wireless', 'wifi-iface', 'mlo0', {
        ssid, key, encryption: 'sae', ieee80211w: '2', mlo: '1',
        mode: 'ap', network: 'lan', device: ['radio1', 'radio2']
    }]);
    assert.equal(button.disabled, false);
    assert.equal(cancel.disabled, false);
    if (failAt) assert.match(status.textContent, /^Failed:/);
    else {
        assert.match(status.textContent, /^Done/);
        assert.deepEqual(calls[3][1], ['/sbin/wifi', ['reload']]);
        assert.equal(uciData.mlo0.key, key);
    }
}

(async () => {
    const radios = ['2g', '5g', '6g'].map((band, i) => ({'.name': 'radio' + i, band}));
    await checkDefaults(radios, ['radio1', 'radio2']);
    await checkDefaults(radios.map(r => ({...r, disabled: r.band === '6g' ? '1' : '0'})), ['radio1', 'radio0']);
    await checkDefaults(radios.map(r => ({...r, disabled: r.band !== '5g' ? '1' : '0'})), undefined);
    await checkDefaults(radios.slice(0, 2), ['radio1', 'radio0']);
    for (const failAt of [null, 'get', 'exists', 'add', 'commit', 'reload']) await checkCreate(failAt);
    const flag = {enabled:'1', disabled:'0'};
    const flagSetup = mlo.slice(mlo.indexOf("o = s.taboption('general', form.Flag, 'mlo'"),
                               mlo.indexOf("o = s.taboption('general', form.ListValue, 'mode'"));
    bind('let o; ' + flagSetup, {s: {taboption: () => flag}, form: {Flag: {}}, _: text => text});
    assert.equal(flag.default, '0', 'Existing single-link sections must not opt into MLO');
    assert.ok(!wifi7.includes("roValue('mld_allowed_links: 0x07"));
    assert.ok(!wifi7.includes("return 'STR mode"));
    console.log('PASS: MLO radio defaults/validation and literal UCI credentials, including transaction failures');
})().catch(error => { console.error(error); process.exitCode = 1; });
