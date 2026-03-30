/**
 * client.js
 * Pure HTTP client for interacting with the Refract registry.
 *
 * Vanilla JS — no framework dependency. Works in any context:
 * plain scripts, React, Vue, Lit components, Node.js tests, etc.
 *
 * Responsibilities:
 * - Load schemas from the registry (/functions/details)
 * - Validate parameters against Python type definitions before each call
 * - Perform HTTP calls (GET/POST) to registered functions
 * - Consume SSE streams as async generators
 *
 * No type coercion — pass the correct JS types matching your Python signatures.
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
    // CORE: CALL & STREAM
    // ========================================================================

    /**
     * Calls a registered function and returns the raw JSON response.
     *
     * Schemas are auto-loaded and cached on the first call — no need to call
     * loadSchemas() manually unless you want to pre-warm the cache.
     *
     * Parameters are validated against the Python type definitions before the
     * request is sent. Pass validate: true to enable this check (recommended
     * for form-driven UIs); leave it off for programmatic callers where types
     * are already correct.
     *
     * The response is returned as-is — it is the serialised form of your
     * Pydantic model. No unwrapping or envelope logic is applied.
     *
     * @param {string} funcName - Name of the registered function
     * @param {object} params - Parameters for the function (correct JS types)
     * @param {object} [options]
     * @param {boolean} [options.validate=false] - Validate params before sending
     * @returns {Promise<any>} JSON response from the server (your Pydantic model)
     *
     * @example
     * const api = new RefractClient();
     * const data = await api.call('add', { a: 1, b: 2 });
     * // → { result: 3 }  (your Pydantic model, as returned by the API)
     */
    async call(funcName, params = {}, { validate = false } = {}) {
        // 1. Resolve schema (auto-load if not cached)
        let schema = this.getSchema(funcName);
        if (!schema) {
            const schemas = await this.loadSchemas();
            schema = schemas[funcName];
            if (!schema) throw new Error(`Function "${funcName}" not found in registry`);
        }

        // 2. Optional validation against Python type definitions
        if (validate) {
            const { valid, errors } = this._validateParams(params, schema);
            if (!valid) {
                const messages = Object.entries(errors)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(', ');
                throw new Error(`Validation failed for "${funcName}": ${messages}`);
            }
        }

        // 3. Build HTTP request
        const method = schema.http_methods[0];
        let url = `/${funcName}`;
        const fetchOptions = {
            method: method.toUpperCase(),
            headers: { 'Content-Type': 'application/json' },
        };

        if (method.toUpperCase() === 'GET') {
            const queryParams = new URLSearchParams();
            for (const [key, val] of Object.entries(params)) {
                if (typeof val === 'object' && val !== null) {
                    queryParams.append(key, JSON.stringify(val));
                } else {
                    queryParams.append(key, val);
                }
            }
            const queryString = queryParams.toString();
            if (queryString) url += `?${queryString}`;
        } else {
            fetchOptions.body = JSON.stringify(params);
        }

        // 4. Fetch and return raw response (your Pydantic model, as-is)
        const response = await fetch(url, fetchOptions);
        if (!response.ok) {
            let errorMsg = `HTTP ${response.status}`;
            try {
                const errorData = await response.json();
                errorMsg = errorData.detail
                    ? (typeof errorData.detail === 'string'
                        ? errorData.detail
                        : JSON.stringify(errorData.detail))
                    : JSON.stringify(errorData);
            } catch {
                errorMsg = response.statusText || errorMsg;
            }
            throw new Error(errorMsg);
        }

        return await response.json();
    }

    /**
     * Async generator that consumes an SSE endpoint and yields parsed events.
     *
     * @param {string} funcName - Name of the registered streaming function
     * @param {object} params - Parameters to send as JSON body
     * @param {object} [options]
     * @param {AbortSignal} [options.signal] - AbortSignal for cancellation
     * @param {boolean} [options.validate=false] - Validate params before sending
     * @yields {{ event: string, data: object|string }} Parsed SSE events
     *
     * @example
     * const api = new RefractClient();
     * for await (const { event, data } of api.stream('stream_words', { text: 'hello world' })) {
     *     if (event === 'token')    console.log(data.chunk);
     *     if (event === 'complete') console.log('Done:', data.message);
     * }
     */
    async *stream(funcName, params = {}, { signal, validate = false } = {}) {
        // Resolve schema (auto-load if not cached) — ensures the function exists
        let schema = this.getSchema(funcName);
        if (!schema) {
            const schemas = await this.loadSchemas();
            schema = schemas[funcName];
            if (!schema) throw new Error(`Function "${funcName}" not found in registry`);
        }

        // Optional validation
        if (validate) {
            const { valid, errors } = this._validateParams(params, schema);
            if (!valid) {
                const messages = Object.entries(errors)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(', ');
                throw new Error(`Validation failed for "${funcName}": ${messages}`);
            }
        }

        const response = await fetch(`/${funcName}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
            signal,
        });

        if (!response.ok) {
            let errorMsg = `HTTP ${response.status}`;
            try {
                const errorData = await response.json();
                errorMsg = errorData.detail
                    ? (typeof errorData.detail === 'string'
                        ? errorData.detail
                        : JSON.stringify(errorData.detail))
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
                    } catch {
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
            } catch {
                yield { event: currentEvent, data: currentData };
            }
        }
    }

    // ========================================================================
    // VALIDATION
    // ========================================================================

    /**
     * Validates a set of parameter values against a function's Python type definitions.
     *
     * Requires schemas to be loaded — call loadSchemas() or make at least one
     * call() first. Throws if schemas are not loaded yet.
     *
     * Useful for form UX: validate on input change before submitting.
     * For programmatic callers, prefer letting the server return a 422 instead.
     *
     * Note: Validation covers primitive types (int, float, str, bool) and
     * collection shapes (list, dict). Complex/Union types pass without error.
     *
     * @param {string} funcName - Name of the registered function
     * @param {object} params - Parameter values to validate
     * @returns {{ valid: boolean, errors: Object.<string, string> }}
     *
     * @example
     * await api.loadSchemas();
     * const { valid, errors } = api.validate('add', { a: 1 });
     * // → { valid: false, errors: { b: 'Required' } }
     */
    validate(funcName, params) {
        if (!this._schemas) {
            throw new Error('Schemas not loaded. Call loadSchemas() or call() first.');
        }
        const schema = this._schemas[funcName];
        if (!schema) throw new Error(`Function "${funcName}" not found in registry`);
        return this._validateParams(params, schema);
    }

    // ========================================================================
    // INTERNAL: PARAM VALIDATION
    // ========================================================================

    /**
     * Validates params against a function schema.
     * @private
     */
    _validateParams(params, schema) {
        const errors = {};

        for (const param of (schema.parameters || [])) {
            const value = params[param.name];

            // Required check
            if (param.required && (value === undefined || value === null)) {
                errors[param.name] = 'Required';
                continue;
            }

            // Skip optional absent params
            if (value === undefined || value === null) continue;

            // Type check — Python type → JS type validation
            const typeError = this._checkType(value, param.type);
            if (typeError) {
                errors[param.name] = typeError;
            }
        }

        return { valid: Object.keys(errors).length === 0, errors };
    }

    /**
     * Checks whether a JS value matches the expected Python type.
     *
     * Covers primitives and collection shapes.
     * Complex/Union/Optional types are not checked — the server validates those.
     *
     * Python → JS type mapping:
     *   int    → number + Number.isInteger()
     *   float  → number
     *   str    → string
     *   bool   → boolean
     *   list   → Array.isArray()
     *   dict   → typeof object + not array
     *   other  → no check (pass through)
     *
     * @private
     * @param {*} value
     * @param {string} pythonType
     * @returns {string|null} Error message, or null if valid
     */
    _checkType(value, pythonType) {
        switch (pythonType) {
            case 'int':
                if (typeof value !== 'number' || !Number.isInteger(value))
                    return 'Expected integer';
                break;
            case 'float':
                if (typeof value !== 'number')
                    return 'Expected number';
                break;
            case 'str':
                if (typeof value !== 'string')
                    return 'Expected string';
                break;
            case 'bool':
                if (typeof value !== 'boolean')
                    return 'Expected boolean';
                break;
            default:
                // Collection shapes — check structural type, ignore element types
                if (/\blist\b/i.test(pythonType) && !Array.isArray(value))
                    return 'Expected array';
                if (/\bdict\b/i.test(pythonType) && (typeof value !== 'object' || Array.isArray(value)))
                    return 'Expected object';
                // Complex types (Optional, Union, custom models) — pass through
        }
        return null;
    }
}
