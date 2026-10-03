'use strict';
// Render the real board status views with inert RPC and a DOM whose E()
// models LuCI dom.append(): a lone string child is assigned to innerHTML,
// array items become text nodes. Config strings must stay text.
// Usage: node tests/test_board_luci_views.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const pkg = path.join(__dirname, '..', 'package');
const payload = '<img src=x onerror=alert(1)>';

function E(tag, attrs, kids) {
    if (attrs == null || typeof attrs !== 'object' || Array.isArray(attrs) || attrs.tag)
        [attrs, kids] = [{}, attrs];
    if (kids != null && !Array.isArray(kids) && !kids.tag) kids = [{html: String(kids)}];
    return {tag, attrs, kids: kids || [], appendChild(child) { this.kids.push(child); return child; }};
}
const walk = n => Array.isArray(n) ? n.flatMap(walk) : n && typeof n === 'object'
    ? [n, ...walk(n.kids)] : [String(n)];
const shown = (node, text) => walk(node).some(n => typeof n === 'string' && n.includes(text));
const markup = (node, text) => walk(node).some(n => n.html != null && n.html.includes(text));

function renderView(file, data) {
    const element = () => ({style: {}, appendChild() {}});
    const view = Function('view', 'poll', 'rpc', 'ui', 'L', 'E', '_', 'document', 'window',
        fs.readFileSync(path.join(pkg, file), 'utf8'))(
        {extend: proto => proto}, {add() {}}, {declare: () => () => Promise.resolve({})}, {},
        {bind: (fn, self) => fn.bind(self)}, E, text => text,
        {getElementById: () => null, createElement: element, querySelector: () => null,
            querySelectorAll: () => [], head: element(), body: element()},
        {getComputedStyle: () => ({backgroundColor: 'rgb(0, 0, 0)'})});
    return view.render(data);
}

let passed = 0, failed = 0;
function check(name, fn) {
    try { fn(); ++passed; console.log('PASS ' + name); }
    catch (error) { ++failed; console.error('FAIL ' + name + ': ' + error.message); }
}

// luci-app-w1700k-fancontrol grants "uci": ["fan"] write, so a delegate can
// store any curve_preset through ubus uci set; getStatus echoes it.
check('fan status shows the UCI curve preset as text', () => {
    const page = renderView('luci-app-w1700k-fancontrol/htdocs/luci-static/resources/view/fan/status.js',
        {uci_mode: 'auto', uci_preset: payload});
    assert(!markup(page, payload), 'preset assigned to innerHTML');
    assert(shown(page, payload), 'preset not shown');
});

// The jitter daemon copies UCI npu-monitor.jitter.target into getJitterResult.
check('FlowSense latency card shows the ping target as text', () => {
    const data = Array(16).fill(null);
    data[9] = {target: payload, available: true};
    const page = renderView('luci-app-airoha-flowsense/htdocs/luci-static/resources/view/airoha_flowsense/status.js',
        data);
    assert(!markup(page, payload), 'target assigned to innerHTML');
    assert(shown(page, payload), 'target not shown');
});

console.log(`${passed} PASS / ${failed} FAIL / 0 SKIP`);
process.exitCode = failed ? 1 : 0;
