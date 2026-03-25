/**
 * controller.js
 * Base controller with pure logic for Refract function elements.
 *
 * LAYER 2: LitElement with state, validation, and API communication.
 * Decoupled from visual presentation.
 *
 * Responsibilities:
 * - Manage parameter, result, and execution state
 * - Validate parameters against the schema (funcInfo)
 * - Delegate HTTP/SSE calls to RefractClient (Layer 1)
 * - Emit custom events for the execution lifecycle
 */

import { LitElement, html } from 'https://cdn.jsdelivr.net/gh/lit/dist@3/core/lit-core.min.js';
import { RefractClient } from './client.js';

/**
 * BASE CONTROLLER (PURE LOGIC)
 * Handles state, validation, and API communication.
 * Decoupled from visual presentation.
 */
export class AutoFunctionController extends LitElement {
    static properties = {
        // Configuration
        funcName: { type: String, attribute: 'func-name' },
        funcInfo: { type: Object, state: true },

        // State
        params: { type: Object, state: true }, // Current parameter values
        result: { type: Object, state: true },
        // Full backend response (envelope)
        envelope: { type: Object, state: true },
        // Convenience metadata (derived from envelope)
        success: { type: Boolean, state: true },
        message: { type: String, state: true },
        errors: { type: Object, state: true },

        // UI Status
        _status: { type: String, state: true },
        _statusMessage: { type: String, state: true },
        _errorMessage: { type: String, state: true },
        _isExecuting: { type: Boolean, state: true }
    };

    constructor() {
        super();
        this.funcName = '';
        this.funcInfo = null;
        this.params = {}; // { paramName: value }
        this.result = null;
        this.envelope = null;
        this.success = undefined;
        this.message = '';
        this.errors = {};

        this._status = 'default';
        this._statusMessage = 'Ready';
        this._errorMessage = '';
        this._isExecuting = false;

        // Layer 1: pure HTTP client (no Lit)
        this._client = new RefractClient();
    }

    async connectedCallback() {
        super.connectedCallback();

        // 1. If we have a name but no info, load it from the registry
        if (this.funcName && !this.funcInfo) {
            try {
                await this.loadFunctionInfo();
            } catch (error) {
                this._errorMessage = error.message;
                this._setStatus('error', 'Error loading function');
            }
        }

        // 2. Initialize params with defaults if funcInfo is already loaded
        if (this.funcInfo && Object.keys(this.params).length === 0) {
            this._initParamsWithDefaults();
        }

        this.dispatchEvent(new CustomEvent('function-connected', {
            detail: { funcName: this.funcName, funcInfo: this.funcInfo },
            bubbles: true,
            composed: true
        }));
    }

    async loadFunctionInfo() {
        const schemas = await this._client.loadSchemas();
        const info = schemas[this.funcName];
        if (!info) {
            throw new Error(`Function "${this.funcName}" not found in registry`);
        }
        this.funcInfo = info;
    }

    // If funcInfo changes, re-initialize defaults
    updated(changedProperties) {
        if (changedProperties.has('funcInfo') && this.funcInfo) {
            this._initParamsWithDefaults();
        }
    }

    _initParamsWithDefaults() {
        const newParams = { ...this.params };
        this.funcInfo?.parameters?.forEach(p => {
            if (newParams[p.name] === undefined && p.default !== null) {
                newParams[p.name] = p.default;
            }
        });
        this.params = newParams;
    }

    // ========================================================================
    // LOGIC API (STATE MANAGEMENT)
    // ========================================================================

    /**
     * Sets the value of a parameter and updates the state.
     */
    setParam(name, value) {
        // Immutable update to trigger Lit reactivity
        this.params = {
            ...this.params,
            [name]: value
        };

        // Clear associated error if it exists
        if (this.errors[name]) {
            const newErrors = { ...this.errors };
            delete newErrors[name];
            this.errors = newErrors;
        }

        this.dispatchEvent(new CustomEvent('params-changed', {
            detail: { params: this.params },
            bubbles: true,
            composed: true
        }));
    }

    getParam(name) {
        return this.params[name];
    }

    getParams() {
        return this.params;
    }

    getResult() {
        return this.result;
    }

    /**
     * Returns the full backend envelope.
     * Useful for consumers that need metadata (reasoning/trajectory/history, etc.).
     */
    getEnvelope() {
        return this.envelope;
    }

    /**
     * Returns the actual payload (alias for result).
     */
    getPayload() {
        return this.result;
    }

    isSuccess() {
        return this.success === true;
    }

    // ========================================================================
    // EXECUTION LOGIC
    // ========================================================================

    /**
     * Executes the function with the current parameters and updates component state.
     *
     * **Envelope unwrap behavior:** The raw API response is always stored in
     * `this.envelope`. If the response is an object with a `result` property,
     * `this.result` is set to `data.result` (the unwrapped payload). Otherwise
     * `this.result` mirrors `this.envelope` directly.
     *
     * ```
     * API response: { result: 42, success: true, message: "" }
     *   → this.envelope = { result: 42, success: true, message: "" }
     *   → this.result   = 42                          // unwrapped
     *
     * API response: { items: ["a", "b"], total: 2 }
     *   → this.envelope = { items: ["a", "b"], total: 2 }
     *   → this.result   = { items: ["a", "b"], total: 2 } // same reference
     * ```
     *
     * The same unwrap logic is applied by the static helper
     * {@link AutoFunctionController.executeFunction}.
     *
     * @returns {Promise<any>} The unwrapped payload (`this.result`).
     * @fires before-execute
     * @fires after-execute
     * @fires execute-error
     */
    async execute() {
        // 1. Validate state (params vs funcInfo)
        if (!this.validate()) {
            this._errorMessage = 'Please fill all required fields and fix errors.';
            this._setStatus('error', 'Validation error');
            return;
        }

        // 2. Pre-execution hook
        const preEvent = new CustomEvent('before-execute', {
            detail: { funcName: this.funcName, params: this.params },
            bubbles: true,
            composed: true,
            cancelable: true
        });

        if (!this.dispatchEvent(preEvent)) {
            console.log('Execution cancelled by before-execute handler');
            return;
        }

        // 3. Setup execution state
        this._isExecuting = true;
        this._setStatus('loading', 'Executing...');
        this._errorMessage = '';

        try {
            // 4. Call API
            const data = await this.callAPI(this.params);

            // Store full envelope
            this.envelope = data;

            // Derive metadata + standardized payload
            const hasEnvelopeShape = (data && typeof data === 'object' && Object.prototype.hasOwnProperty.call(data, 'result'));
            this.result = hasEnvelopeShape ? data.result : data;

            if (data && typeof data === 'object') {
                this.success = data.success;
                this.message = data.message;
            } else {
                this.success = undefined;
                this.message = '';
            }

            // If the backend returns success=false, treat it as a failed execution
            // (but do NOT throw: left to the consumer's discretion)
            if (this.success === false) {
                this._errorMessage = this.message || 'Execution error';
                this._setStatus('error', 'Execution error');
            } else {
                this._errorMessage = '';
                this._setStatus('success', 'Executed successfully');
            }

            const payload = this.result;

            this.dispatchEvent(new CustomEvent('after-execute', {
                detail: { funcName: this.funcName, params: this.params, result: payload, envelope: this.envelope },
                bubbles: true,
                composed: true
            }));

            return payload;
        } catch (error) {
            this.result = { _isError: true, _message: `Error: ${error.message}` };
            this.envelope = this.result;
            this.success = false;
            this.message = this.result._message;
            this._setStatus('error', 'Execution error');

            this.dispatchEvent(new CustomEvent('execute-error', {
                detail: { funcName: this.funcName, params: this.params, error },
                bubbles: true,
                composed: true
            }));

            throw error;
        } finally {
            this._isExecuting = false;
        }
    }

    /**
     * Validates the current parameters against the definition (funcInfo).
     * Does NOT depend on the DOM.
     */
    validate() {
        let isValid = true;
        const newErrors = {};

        this.funcInfo?.parameters?.forEach(param => {
            const value = this.params[param.name];
            let error = null;

            // Required check
            if (param.required) {
                if (value === undefined || value === null || (typeof value === 'string' && value.trim() === '')) {
                    // Checkbox/Boolean required usually ignored unless specified true needed
                    if (param.type !== 'bool') {
                        error = 'Required field';
                    }
                }
            }

            // Type check (basic)
            if (!error && value !== undefined && value !== null && value !== '') {
                if (param.type === 'int') {
                    if (!Number.isInteger(Number(value))) error = 'Must be an integer';
                } else if (param.type === 'float') {
                    if (isNaN(parseFloat(value))) error = 'Must be a decimal number';
                } else if (this._isComplexType(param.type)) {
                    // If it's a string (from textarea), try to parse it
                    if (typeof value === 'string') {
                        try {
                            JSON.parse(value);
                        } catch (e) {
                            error = 'Invalid JSON';
                        }
                    }
                }
            }

            if (error) {
                isValid = false;
                newErrors[param.name] = error;
            }
        });

        this.errors = newErrors;
        return isValid;
    }

    /**
     * Processes parameters applying type conversions according to the funcInfo definition.
     * Delegates to RefractClient._processParams(); uses this.funcInfo as fallback.
     * @param {object} params - Raw parameters
     * @param {object|null} funcInfoOverride - Alternative funcInfo (for streaming with a different function)
     * @returns {object} Processed parameters with correct types
     */
    _processParams(params, funcInfoOverride = null) {
        return this._client._processParams(params, funcInfoOverride || this.funcInfo);
    }

    async callAPI(params) {
        return this._client.call(this.funcName, params, this.funcInfo);
    }

    /**
     * Async generator that consumes an SSE endpoint and yields parsed events.
     * Delegates to RefractClient.stream().
     * @param {string} endpoint - Endpoint name (used as URL: /{endpoint})
     * @param {object} params - Parameters to send as JSON body
     * @param {object|null} funcInfo - FuncInfo for type processing (optional)
     * @yields {{ event: string, data: object|string }} Parsed SSE events
     */
    async *callStreamAPI(endpoint, params, funcInfo = null, options = {}) {
        yield* this._client.stream(endpoint, params, funcInfo || this.funcInfo, options);
    }

    /**
     * Static helper to execute functions without creating DOM elements.
     * Useful for inter-function calls (e.g. chat calling calculate_context_usage).
     *
     * @param {string} funcName - Name of the registered function
     * @param {object} params - Parameters for the function
     * @returns {Promise<any>} - Execution result
     * @throws {Error} - If the function does not exist or execution fails
     *
     * @example
     * const result = await AutoFunctionController.executeFunction('my_func', { x: 1 });
     */
    static async executeFunction(funcName, params) {
        const client = new RefractClient();
        try {
            const schemas = await client.loadSchemas();
            const funcInfo = schemas[funcName];
            if (!funcInfo) throw new Error(`Function "${funcName}" not found in registry`);

            const data = await client.call(funcName, params, funcInfo);

            // Same unwrap logic as execute(): extract payload from envelope
            const hasEnvelopeShape = (data && typeof data === 'object' && Object.prototype.hasOwnProperty.call(data, 'result'));
            return hasEnvelopeShape ? data.result : data;
        } catch (error) {
            console.error(`❌ Error executing function "${funcName}":`, error);
            throw error;
        }
    }

    // Internal helpers
    _isComplexType(type) {
        if (!type) return false;
        return /\b(dict|list)\b|json/i.test(type);
    }

    _setStatus(type, message) {
        this._status = type;
        this._statusMessage = message;
    }

    // Default render: nothing visual, just slot
    render() {
        return html`<slot></slot>`;
    }
}

// Register custom element
if (!customElements.get('auto-function-controller')) {
    customElements.define('auto-function-controller', AutoFunctionController);
}
