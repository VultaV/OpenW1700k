# Wireless runtime regression fixture

Sanitized model of the live LuCI browser data captured on 2026-10-03.
The section names, interface names, `device` value types, `mlo` flags and
disabled state reproduce the reported failure. SSIDs and unrelated values
are synthetic; there are no credentials, client identifiers or packets.

`uci-wireless.json` preserves the value types returned by LuCI UCI. In
particular, `default_radio2.device` is `["radio2"]`, **not** `"radio2"`.
`uci show` prints both forms alike and cannot recover that distinction.
The section is disabled, has `mlo: "0"`, and has no runtime interface.
The active `default_radio1` uses `["radio1", "radio2"]` and `ap-mld0`.

Pass this directory as the optional evidence argument to the runtime test,
or omit the argument to use it by default. External evidence directories
must provide these same two JSON files; the test does not infer UCI types
from `uci-wireless.txt`.

`tests/test_wireless_runtime.js` runs the complete network and Wireless
modules with fake form/DOM/RPC plumbing. It exercises all overview rows,
the registered status poll, a disabled-network modal status badge, and a
synthetic associated-station row.

For the actual LuCI form rendering path, `tests/test_wireless_form_runtime.js`
also loads captured `form.js` and the Class/DOM code from `luci.js`. It requires the external
`linkedom` Node package (available through Node's normal module resolution,
or `NODE_PATH`) and a local directory containing those captures. Both
harnesses remain host tests; real-browser verification is separate.
