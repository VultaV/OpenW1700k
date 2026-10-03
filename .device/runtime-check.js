// Paste into the live LuCI console. Reload the page to undo.
// The private netid helper is reached through synchronous class hooks;
// normalize only its reads, without changing UCI objects or saved config.
(async () => {
    const [network, uci] = await Promise.all([L.require('network'), L.require('uci')]);
    const np = Object.getPrototypeOf(network);
    const wp = Object.getPrototypeOf(network.instantiateWifiNetwork('__runtime_check__'));

    wp.getDevice = function() {
        const ifname = this.getIfname();
        return ifname != null ? np.instantiateDevice.call(network, ifname) : null;
    };

    for (const name of ['lookupWifiNetwork', 'instantiateDevice']) {
        const original = np[name];
        np[name] = function(...args) {
            const get = uci.get;
            uci.get = function(config, section, option) {
                const s = get.apply(this, arguments);
                return config === 'wireless' && option == null &&
                    s?.['.type'] === 'wifi-iface' &&
                    Array.isArray(s.device) && s.device.length === 1
                    ? {...s, device: s.device[0]} : s;
            };
            try { return original.apply(this, args); }
            finally { uci.get = get; }
        };
    }

    // getDevice(sid) also calls the private helper after an asynchronous load.
    const getDevice = np.getDevice;
    np.getDevice = async function(name) {
        const device = await getDevice.call(this, name);
        const s = uci.get('wireless', name);
        return device == null && s?.['.type'] === 'wifi-iface' &&
            Array.isArray(s.device) && s.device.length === 1
            ? this.lookupWifiNetwork(name).getDevice() : device;
    };
})();
