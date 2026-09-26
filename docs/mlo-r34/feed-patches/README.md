# r34 LuCI feed patch

`0003-luci-attendedsysupgrade-github-update.patch` applies to the LuCI feed at
`289a7260434d4b8212a9cc6cf6160cb1935270c1`. It publishes the GitHub release
selector and authenticated download flow previously present only in the local
build feed. The existing `github_check` and `github_fetch` CGI helpers from the
public overlay must still be included in the image.

The patch starts from that pinned upstream view, preserving its non-factory
image fallback and controlled errors for empty main/rebuilder results. It also
retains upstream error-detail formatting, upload mode `0o600`, translations and
EFI detection. GitHub upgrade RPC errors reject instead of scheduling a
successful reconnect. The unused local `file.exec` declaration is omitted.

The package version is explicitly `26.250.72430~e81743d-r2`; an uncommitted feed
patch alone would not update LuCI's Git-derived package version.

Apply to a clean, pinned LuCI feed (paths below are placeholders):

```sh
git -C /path/to/luci-feed apply --check /path/to/0003-luci-attendedsysupgrade-github-update.patch
git -C /path/to/luci-feed apply /path/to/0003-luci-attendedsysupgrade-github-update.patch
node tests/test_attendedsysupgrade_images.js /path/to/luci-feed/applications/luci-app-attendedsysupgrade/htdocs/luci-static/resources/view/attendedsysupgrade/overview.js
```

Do not apply over or discard an existing local feed diff. The earlier packages
feed patches documented under `docs/mlo-r29/` and `docs/mlo-r30/` are separate.
Record this patch and both patched files in the new build manifest:

| File relative to LuCI feed | SHA256 after patch |
| --- | --- |
| `applications/luci-app-attendedsysupgrade/Makefile` | `f317c6f567e98da2e3389ae7a7a356506a9da5ca1303b7ed533bfdd4bf449c66` |
| `applications/luci-app-attendedsysupgrade/htdocs/luci-static/resources/view/attendedsysupgrade/overview.js` | `3ec3f78e3aaebfbfebfc73fe61148e31f43fe4d138168d90941e12d22fb7298f` |

Validation before integration: the real local r33 view produced **6 PASS / 3
FAIL / 0 SKIP**; a fresh pinned copy plus this patch produced **9 PASS / 0 FAIL /
0 SKIP**. The three failures covered the missing fallback and undefined image
access in the main/rebuilder paths. Patch application recreated the expected
view and Makefile byte-for-byte.

The test executes the full view with inert RPC, HTTP and DOM substitutes and
accepts an extracted image's `overview.js` as its first argument. It checks image
selection and upgrade error handling without fetching or flashing anything.
These checks do not establish a full browser flow, clean image build or boot.
