/**
 * client.js
 * Pure HTTP client for interacting with the Refract registry.
 *
 * LAYER 1: Vanilla JS, no dependency on Lit or the DOM.
 * Can be used in any context (Lit components, vanilla JS, tests, etc.).
 *
 * Responsibilities:
 * - Load schemas from the registry (/functions/details)
 * - Perform HTTP calls (GET/POST) to registered functions
 * - Consume SSE streams as async generators
 * - Process/coerce parameter types according to the schema
 */
export class RefractClient {
    constructor() {
        /** @type {Object.<string, Object>|null} Schemas loaded from /functions/details */
        this._schemas = null;
    }

    // ========================================================================
    // SCHEMA MANAGEMENT
    // ========================================================================

    /**
     * Loads all schemas from the registry via /functions/details.
     * The result is cached in this._schemas.
     *
     * @returns {Promise<Object.<string, Object>>} Map of funcName → funcInfo
     */
    async loadSchemas() {
        const response = await fetch('/functions/details');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        this._schemas = data.functions;
        return this._schemas;
    }

    /**
     * Returns the schema (funcInfo) for a specific function.
     * Requires loadSchemas() to have been called first, or returns null.
     *
     * @param {string} funcName
     * @returns {Object|null}
     */
    getSchema(funcName) {
        if (!this._schemas) return null;
        return this._schemas[funcName] || null;
    }

    // ========================================================================
    // HTTP CALLS
    // ========================================================================

    /**
     * Executes an HTTP call to a registered function.
     * Supports GET and POST based on the http_methods in the schema.
     * Returns the raw server response (the "envelope").
     *
     * @param {string} funcName - Name of the registered function
     * @param {object} params - Parameters for the function
     * @param {object|null} funcInfo - Function schema (optional; auto-loaded if not provided)
     * @returns {Promise<any>} JSON response from the server
     */
    async call(funcName, params, funcInfo = null) {
        let info = funcInfo || this.getSchema(funcName);

        // Auto-load schemas if not available
        if (!info) {
            const schemas = await this.loadSchemas();
            info = schemas[funcName];
            if (!info) throw new Error(`Function "${funcName}" not found in registry`);
        }

        const method = info.http_methods[0];
        let url = `/${funcName}`;
        const fetchOptions = {
            method: method.toUpperCase(),
            headers: { 'Content-Type': 'application/json' }
        };

        const processedParams = this._processParams(params, info);

        if (method.toUpperCase() === 'GET') {
            const queryParams = new URLSearchParams();
            for (const [key, val] of Object.entries(processedParams)) {
                if (typeof val === 'object' && val !== null) {
                    queryParams.append(key, JSON.stringify(val));
                } else {
                    queryParams.append(key, val);
                }
            }
            const queryString = queryParams.toString();
            if (queryString) url += `?${queryString}`;
        } else {
            fetchOptions.body = JSON.stringify(processedParams);
        }

        const response = await fetch(url, fetchOptions);
        if (!response.ok) {
            let errorMsg = `HTTP ${response.status}`;
            try {
                const errorData = await response.json();
                errorMsg = errorData.detail
                    ? (typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail))
                    : JSON.stringify(errorData);
            } catch {
                errorMsg = response.statusText || errorMsg;
            }
            throw new Error(errorMsg);
        }

        return await response.json();
    }

    // ========================================================================
    // SSE STREAMING
    // ========================================================================

    /**
     * Async generator that consumes an SSE endpoint and yields parsed events.
     *
     * @param {string} endpoint - Endpoint name (URL: /{endpoint})
     * @param {object} params - Parameters to send as JSON body
     * @param {object|null} funcInfo - FuncInfo for type processing (optional)
     * @param {object} options - Additional options (e.g. { signal: AbortSignal })
     * @yields {{ event: string, data: object|string }} Parsed SSE events
     */
    async *stream(endpoint, params, funcInfo = null, options = {}) {
        const processedParams = this._processParams(params, funcInfo);

        const response = await fetch(`/${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(processedParams),
            signal: options.signal,
        });

        if (!response.ok) {
            let errorMsg = `HTTP ${response.status}`;
            try {
                const errorData = await response.json();
                errorMsg = errorData.detail
                    ? (typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail))
                    : JSON.stringify(errorData);
            } catch {
                errorMsg = response.statusText || errorMsg;
            }
            throw new Error(errorMsg);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let currentEvent = null;
        let currentData = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    currentEvent = line.slice(7).trim();
                } else if (line.startsWith('data: ')) {
                    currentData = line.slice(6);
                } else if (line === '' && currentEvent && currentData) {
                    try {
                        yield { event: currentEvent, data: JSON.parse(currentData) };
                    } catch (e) {
                        yield { event: currentEvent, data: currentData };
                    }
                    currentEvent = null;
                    currentData = '';
                }
            }
        }

        // Process remaining buffer content after stream ends
        if (buffer) {
            if (buffer.startsWith('event: ')) {
                currentEvent = buffer.slice(7).trim();
            } else if (buffer.startsWith('data: ')) {
                currentData = buffer.slice(6);
            }
        }

        // Flush pending event if stream ends without trailing \n\n
        if (currentEvent && currentData) {
            try {
                yield { event: currentEvent, data: JSON.parse(currentData) };
            } catch (e) {
                yield { event: currentEvent, data: currentData };
            }
        }
    }

    // ========================================================================
    // PARAM PROCESSING
    // ========================================================================

    /**
     * Processes parameters applying type conversions according to the schema (funcInfo).
     * Converts strings to JSON for complex types (dict/list), int, float.
     *
     * @param {object} params - Raw parameters
     * @param {object|null} funcInfo - Function schema (used to determine types)
     * @returns {object} Parameters with correct types
     */
    _processParams(params, funcInfo = null) {
        const processedParams = {};
        Object.entries(params).forEach(([key, val]) => {
            const paramDef = funcInfo?.parameters?.find(p => p.name === key);
            if (paramDef && this._isComplexType(paramDef.type) && typeof val === 'string') {
                try {
                    processedParams[key] = JSON.parse(val);
                } catch {
                    processedParams[key] = val;
                }
            } else if (paramDef && paramDef.type === 'int') {
                processedParams[key] = parseInt(val);
            } else if (paramDef && paramDef.type === 'float') {
                processedParams[key] = parseFloat(val);
            } else {
                processedParams[key] = val;
            }
        });
        return processedParams;
    }

    /**
     * Determines whether a parameter type is complex (dict, list, JSON).
     *
     * @param {string|null} type
     * @returns {boolean}
     */
    _isComplexType(type) {
        if (!type) return false;
        return /\b(dict|list)\b|json/i.test(type);
    }
}
