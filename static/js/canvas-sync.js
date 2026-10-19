(function () {
    'use strict';

    function startCanvasSyncSocket(options) {
        const config = options || {};
        const clientId = String(config.clientId || '').trim();
        const onMessage = typeof config.onMessage === 'function' ? config.onMessage : function () {};
        const host = window.location.host;
        if (!host) return function () {};

        const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        let socket = null;
        let retryTimer = null;
        let stopped = false;

        const connect = () => {
            if (stopped) return;
            try {
                socket = new WebSocket(
                    `${protocol}://${host}/ws/stats?client_id=${encodeURIComponent(clientId)}`
                );
            } catch (error) {
                retryTimer = window.setTimeout(connect, 3000);
                return;
            }
            socket.onmessage = (event) => {
                try {
                    onMessage(JSON.parse(event.data));
                } catch (error) {
                    // Ignore malformed broadcast messages and keep the socket alive.
                }
            };
            socket.onclose = () => {
                if (!stopped) retryTimer = window.setTimeout(connect, 3000);
            };
            socket.onerror = () => {
                try { socket.close(); } catch (error) {}
            };
        };

        const stop = () => {
            stopped = true;
            window.clearTimeout(retryTimer);
            try { socket?.close(); } catch (error) {}
        };

        window.addEventListener('beforeunload', stop, { once: true });
        connect();
        return stop;
    }

    window.startCanvasSyncSocket = startCanvasSyncSocket;
})();
