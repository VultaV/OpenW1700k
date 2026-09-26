'use strict';
// Execute the real LuCI view with inert RPC, request, and DOM substitutes.
// Usage: node tests/test_attendedsysupgrade_images.js /path/to/overview.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = process.argv[2];
assert(source, 'Pass the patched LuCI attendedsysupgrade overview.js');
const code = fs.readFileSync(source, 'utf8');
String.prototype.format = function(...args) {
    let index = 0;
    return this.replace(/%[sd]/g, () => String(args[index++]));
};

let response, download, rpcFailure = false;
const calls = [], modals = [], timers = [];
const status = {};
const rpc = {
    getSessionID: () => 'offline-session',
    declare(spec) {
        return async (...args) => {
            calls.push({spec, args});
            if (spec.method === 'upgrade_start') {
                assert.equal(spec.reject, true);
                if (rpcFailure) throw Error('upgrade rejected');
            }
        };
    }
};
const ui = {
    showModal: (title, body) => modals.push({title, body}),
    hideModal() {},
    createHandlerFn: (self, fn, ...args) => fn.bind(self, ...args),
    awaitReconnect: () => assert.fail('No live reconnect may run')
};
const E = (tag, attrs, children) => ({tag, attrs, children});
const v = Function('view', 'rpc', 'poll', 'ui', 'request', 'uci', 'fs', 'form',
    'E', '_', 'document', 'fetch', 'setTimeout', code)(
    {extend: x => x}, rpc, {remove() {}}, ui,
    {request: () => ({then: fn => fn(response)})}, {}, {}, {}, E, x => x,
    {getElementById: () => status},
    async (url, options) => { calls.push({url, options}); return download; },
    (fn, delay) => timers.push({fn, delay}));
const firmware = {filesystem: 'squashfs', target: 'airoha/an7581'};
const image = (type, filesystem = 'squashfs') => ({type, filesystem, name: type + '.bin'});
let passed = 0, failed = 0;
async function check(name, fn) {
    try { await fn(); ++passed; console.log('PASS ' + name); }
    catch (error) { ++failed; console.error('FAIL ' + name + ': ' + error.message); }
}

(async () => {
    await check('normal sysupgrade preferred to factory image', () => {
        const images = [image('factory'), image('sysupgrade')];
        assert.equal(v.selectImage(images, {}, firmware), images[1]);
    });
    await check('filesystem filter and unambiguous non-factory fallback', () => {
        const images = [image('sysupgrade', 'ext4'), image('factory'), image('trx')];
        assert.equal(v.selectImage(images, {}, firmware), images[2]);
    });
    await check('ambiguous fallback and factory-only images rejected', () => {
        assert.equal(v.selectImage([image('trx'), image('other')], {}, firmware), undefined);
        assert.equal(v.selectImage([image('factory')], {}, firmware), undefined);
    });
    await check('EFI and non-EFI selection preserved', () => {
        const images = [image('combined'), image('combined-efi')];
        const x86 = {...firmware, target: 'x86/64'};
        assert.equal(v.selectImage(images, {efi: true}, x86), images[1]);
        assert.equal(v.selectImage(images, {efi: false}, x86), images[0]);
    });
    await check('empty or incompatible main result shows controlled error', () => {
        for (const images of [[], [image('factory')], [image('sysupgrade', 'ext4')]]) {
            modals.length = 0;
            v.handle200({json: () => ({images})}, null, {}, firmware);
            assert.equal(modals.at(-1).title, 'No sysupgrade image found');
        }
    });
    await check('empty rebuilder result shows warning without dereference', () => {
        response = {status: 200, json: () => ({images: []})};
        v.rebuilder_polls = {offline: () => {}};
        v.handleRequest('offline', false, {}, {}, firmware);
        assert.equal(status.innerText, '⚠️ offline');
    });
    await check('GitHub UI methods and explicit install request retained', async () => {
        assert.equal(typeof v.handleGithubFirmware, 'function');
        assert.equal(typeof v.handleGithubInstall, 'function');
        calls.length = 0; timers.length = 0;
        download = {ok: true, json: async () => ({success: true})};
        await v.handleGithubInstall('test-release', true);
        assert.equal(calls[0].url, '/cgi-bin/github_fetch');
        assert.equal(calls[0].options.method, 'POST');
        assert.deepEqual(JSON.parse(calls[0].options.body),
            {tag: 'test-release', sessionid: 'offline-session'});
        assert.equal(calls[1].spec.method, 'upgrade_start');
        assert.deepEqual(calls[1].args, [true]);
        assert.equal(timers.length, 1);
    });
    await check('GitHub download denial cannot start upgrade', async () => {
        calls.length = 0; timers.length = 0;
        download = {ok: false, json: async () => ({error: 'permission denied'})};
        await v.handleGithubInstall('test-release', true);
        assert.equal(calls.length, 1);
        assert.equal(timers.length, 0);
        assert.equal(modals.at(-1).title, 'Download Error');
    });
    await check('rejected upgrade cannot schedule successful reconnect', async () => {
        timers.length = 0; rpcFailure = true;
        download = {ok: true, json: async () => ({success: true})};
        await v.handleGithubInstall('test-release', false);
        assert.equal(timers.length, 0);
        assert.equal(modals.at(-1).title, 'Download Error');
    });
    console.log(`${passed} PASS / ${failed} FAIL / 0 SKIP`);
    process.exitCode = failed ? 1 : 0;
})().catch(error => { console.error(error); process.exitCode = 1; });
