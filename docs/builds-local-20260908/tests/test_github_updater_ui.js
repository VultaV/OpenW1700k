/* Run with node tests/test_github_updater_ui.js; all browser/RPC effects are mocked. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../user/default/files/overview.js'), 'utf8');
String.prototype.format = function(...args) { let i = 0; return this.replace(/%s/g, () => args[i++]); };

(async () => {
	for (const scenario of ['success', 'download error', 'HTTP error', 'unexpected reply', 'RPC error']) {
		let upgrades = 0, reconnects = 0;
		const modals = [];
		const ui = { showModal: (...args) => modals.push(args), awaitReconnect: () => reconnects++ };
		const rpc = {
			getSessionID: () => '1'.repeat(32),
			declare: options => () => {
				assert.equal(options.method, 'upgrade_start');
				assert.equal(options.reject, true, 'ubus errors must reject');
				upgrades++;
				return scenario === 'RPC error' ? Promise.reject(new Error('Permission denied')) : Promise.resolve(0);
			},
		};
		const fetch = async (url, options) => {
			assert.equal(url, '/cgi-bin/github_fetch');
			assert.equal(options.method, 'POST');
			assert.deepEqual(JSON.parse(options.body), { tag: 'tag/with+symbols', sessionid: '1'.repeat(32) });
			return { ok: scenario !== 'HTTP error', json: async () => scenario === 'download error'
				? { error: 'Checksum mismatch' } : { success: scenario !== 'unexpected reply' } };
		};
		const view = new Function('view', 'rpc', 'ui', 'E', '_', 'fetch', 'setTimeout', source)(
			{ extend: value => value }, rpc, ui, (...args) => args, value => value, fetch,
			callback => callback());
		await view.handleGithubInstall('tag/with+symbols', true);
		assert.equal(upgrades, ['success', 'RPC error'].includes(scenario) ? 1 : 0, scenario);
		assert.equal(reconnects, scenario === 'success' ? 1 : 0, scenario);
		if (scenario !== 'success')
			assert.match(modals.at(-1)[0], /Error/, scenario);
		console.log('PASS UI', scenario);
	}
})().catch(error => { console.error(error); process.exitCode = 1; });
