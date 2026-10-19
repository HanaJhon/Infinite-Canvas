(function (global) {
    const TOKEN_KEY = 'modelscope_api_token';

    global.getModelScopeTokenState = async function () {
        let apiKey = '';
        try {
            apiKey = (localStorage.getItem(TOKEN_KEY) || '').trim();
        } catch (e) {}

        let hasToken = Boolean(apiKey);
        try {
            const response = await fetch('/api/config/token');
            if (response.ok) {
                const data = await response.json();
                if (data.has_token === true) {
                    // The server-side token must win over stale browser storage.
                    hasToken = true;
                    apiKey = '';
                }
            }
        } catch (e) {}

        return { hasToken, apiKey };
    };
})(window);
