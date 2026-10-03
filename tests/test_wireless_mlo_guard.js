'use strict';
// Run the standard Network > Wireless actions touched by the LuCI feed patch
// 0004 with inert UCI and no RPC or device access. E() models LuCI
// dom.append(): a lone string child goes to innerHTML, array items are text.
// Usage: node tests/test_wireless_mlo_guard.js /path/to/luci-feed/modules/luci-mod-network/htdocs/luci-static/resources/view/network/wireless.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const file = process.argv[2];
assert(file, 'Pass the patched LuCI view/network/wireless.js');
const source = fs.readFileSync(file, 'utf8');

function between(start, end) {
    const from = source.indexOf(start);
    assert(from >= 0, 'missing ' + JSON.stringify(start));
    const to = source.indexOf(end, from + start.length);
    assert(to >= 0, 'missing ' + JSON.stringify(end));
    return source.slice(from, to);
}
function E(tag, attrs, kids) {
    if (attrs == null || typeof attrs !== 'object' || Array.isArray(attrs) || attrs.tag)
        [attrs, kids] = [{}, attrs];
    if (kids != null && !Array.isArray(kids) && !kids.tag) kids = [{html: String(kids)}];
    return {tag, attrs, kids: kids || []};
}
const walk = n => Array.isArray(n) ? n.flatMap(walk) : n && typeof n === 'object'
    ? [n, ...walk(n.kids)] : [String(n)];
// luci.js LuCI.toArray()
const L = {
    toArray: v => v == null ? [] : Array.isArray(v) ? v : typeof v === 'object' ? [v]
        : String(v).trim() === '' ? [] : String(v).trim().split(/\s+/),
    url: path => '/cgi-bin/luci/' + path,
    bind: (fn, self, ...args) => fn.bind(self, ...args)
};
function setup(target) {
    const cfg = {
        radio1: {disabled: '0'}, radio2: {disabled: '0'},
        mlo1: {'.name': 'mlo1', device: ['radio1', 'radio2'], disabled: '0'},
        target: {'.name': 'target', disabled: '0', ...target}
    };
    const env = {cfg, writes: [], notices: [], applied: 0};
    env.uci = {
        get: (_, sid, key) => { assert.equal(typeof sid, 'string'); return cfg[sid]?.[key]; },
        set: (_, sid, key, value) => { env.writes.push([sid, key, value]); cfg[sid][key] = value; },
        unset: (_, sid, key) => { env.writes.push([sid, key]); delete cfg[sid][key]; },
        sections: () => [cfg.target, cfg.mlo1].filter(Boolean)
    };
    env.ui = {addNotification: (title, node) => env.notices.push(node),
        changes: {apply: () => ++env.applied}};
    return env;
}
async function updown(target, withMlo = true) {
    const env = setup(target);
    if (!withMlo) delete env.cfg.mlo1;
    const fn = Function('uci', 'ui', 'E', '_', 'L',
        between('function network_updown(', 'function next_free_sid(') + 'return network_updown;')(
        env.uci, env.ui, E, x => x, L);
    await fn('target', {save: async () => {}});
    return env;
}

let passed = 0, failed = 0;
async function check(name, fn) {
    try { await fn(); ++passed; console.log('PASS ' + name); }
    catch (error) { ++failed; console.error('FAIL ' + name + ': ' + error.message); }
}

(async () => {
    // Pinned network_updown compared the scalar radio with ==, so a list
    // device on an MLO section did not count and the shared radio went down.
    await check('disabling a single-radio network keeps a radio an MLO network uses', async () => {
        for (const device of ['radio1', ['radio1']]) {
            const env = await updown({device});
            assert.equal(env.cfg.radio1.disabled, '0', 'MLO still needs radio1');
            assert.deepEqual(env.writes, [['target', 'disabled', '1']]);
            assert.equal(env.applied, 1);
        }
    });
    await check('disabling the last network on a radio still disables the radio', async () => {
        const env = await updown({device: 'radio1'}, false);
        assert.equal(env.cfg.radio1.disabled, '1');
        assert.equal(env.applied, 1);
    });
    // Pinned code passed the device list as a UCI section name.
    await check('Enable/Disable leaves a multi-radio network to the MLO page', async () => {
        const env = await updown({device: ['radio1', 'radio2']});
        assert.deepEqual(env.writes, []);
        assert.equal(env.applied, 0);
        assert.equal(env.notices.length, 1);
        assert(!walk(env.notices).some(n => n.html != null), 'notice assigned to innerHTML');
    });
    await check('Edit leaves a multi-radio network to the MLO page', async () => {
        const opened = [];
        for (const device of [['radio1', 'radio2'], 'radio1']) {
            const env = setup({device});
            const s = {renderMoreOptionsModal(sid) { opened.push(sid); return Promise.resolve(); }};
            Function('s', 'uci', 'ui', 'E', '_', 'L',
                between('const renderWirelessModal = s.renderMoreOptionsModal;', 's.addModalOptions ='))(
                s, env.uci, env.ui, E, x => x, L);
            await s.renderMoreOptionsModal('target');
            assert.equal(env.notices.length, Array.isArray(device) ? 1 : 0);
        }
        assert.deepEqual(opened, ['target'], 'only the single-radio modal opens');
    });
    await check('page notice names multi-radio sections as text and links the MLO page', () => {
        const env = setup({device: ['radio1', 'radio2'], '.name': 'mlo<b>2</b>'});
        const prepended = [];
        Function('uci', 'E', '_', 'L', 'nodes',
            between('return m.render().then(L.bind(function(m, nodes) {', 'poll.add(')
                .replace(/^.*\n/, ''))(env.uci, E, x => x, L, {prepend: n => prepended.push(n)});
        assert.equal(prepended.length, 1);
        const items = walk(prepended);
        assert(!items.some(n => n.html != null), 'notice assigned to innerHTML');
        assert(items.some(n => typeof n === 'string' && n.includes('mlo<b>2</b>, mlo1')), 'names not shown');
        assert(items.some(n => n.tag === 'a' && n.attrs.href === '/cgi-bin/luci/admin/network/mlo'));
    });
    console.log(`${passed} PASS / ${failed} FAIL / 0 SKIP`);
    process.exitCode = failed ? 1 : 0;
})();
