/**
 * element.js
 * Generic "Card" UI for functions in the Refract registry.
 *
 * LAYER 2 (self-contained): Extends LitElement directly.
 * Uses RefractClient internally (composition, not inheritance).
 * Uses Shadow DOM. NOT DESIGNED TO BE EXTENDED.
 *
 * Responsibilities:
 * - Manage parameter, result, and execution state
 * - Validate parameters against the schema (funcInfo)
 * - Delegate HTTP calls to RefractClient (Layer 1)
 * - Render automatic forms based on the schema (funcInfo)
 * - Display results and execution states
 * - Adapt the input type based on the parameter type
 */

import { LitElement, css, html } from 'https://cdn.jsdelivr.net/gh/lit/dist@3/core/lit-core.min.js';
import { RefractClient } from './client.js';

/**
 * GENERIC UI (CARD)
 * Self-contained visual component for any registered Refract function.
 * Uses Shadow DOM.
 * NOT DESIGNED TO BE EXTENDED.
 */
export class AutoFunctionElement extends LitElement {
    static properties = {
        // Configuration
        funcName: { type: String, attribute: 'func-name' },
        funcInfo: { type: Object, state: true },

        // State
        params: { type: Object, state: true },   // Current parameter values
        result: { type: Object, state: true },
        envelope: { type: Object, state: true },  // Full backend response
        success: { type: Boolean, state: true },
        message: { type: String, state: true },
        errors: { type: Object, state: true },

        // UI Status
        _status: { type: String, state: true },
        _statusMessage: { type: String, state: true },
        _errorMessage: { type: String, state: true },
        _isExecuting: { type: Boolean, state: true }
    };

    static styles = css`
        :host { display: block; font-family: system-ui, sans-serif; }
        .container {
            display: flex; flex-direction: column; gap: 1rem; padding: 1rem;
            border: 1px solid #e5e7eb; border-radius: 0.5rem; background: #ffffff;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .header { display: flex; flex-direction: column; gap: 0.5rem; }
        .header-row { display: flex; justify-content: space-between; align-items: center; }
        .title { font-size: 1.25rem; font-weight: 600; margin: 0; color: #1f2937; }
        .description { font-size: 0.875rem; color: #6b7280; font-style: italic; margin: 0; }

        .error-banner {
            padding: 0.75rem; background: #fee2e2; border: 1px solid #fca5a5;
            border-radius: 0.5rem; color: #991b1b; font-size: 0.875rem;
        }

        /* Inputs */
        .params { display: flex; flex-direction: column; gap: 0.75rem; }
        .param-group { display: flex; flex-direction: column; gap: 0.25rem; }
        .param-label { font-size: 0.875rem; font-weight: 600; color: #374151; }
        .param-required { color: #ef4444; }
        .param-desc { font-size: 0.75rem; color: #6b7280; margin: 0; }
        .field-error { font-size: 0.75rem; color: #ef4444; }

        input, select, textarea {
            padding: 0.5rem; border: 1px solid #d1d5db; border-radius: 0.5rem;
            font-size: 0.875rem; width: 100%; box-sizing: border-box;
            background: #fff; color: #1f2937;
        }
        input:focus, select:focus, textarea:focus {
            outline: none; border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
        }
        input.error, select.error, textarea.error { border-color: #ef4444; background: #fef2f2; }

        .checkbox-wrapper { display: flex; align-items: center; gap: 0.5rem; }
        input[type="checkbox"] { width: 1rem; height: 1rem; accent-color: #6366f1; }

        /* Button */
        .execute-btn {
            padding: 0.5rem 1rem; background: linear-gradient(to right, #4f46e5, #7c3aed);
            color: white; border: none; border-radius: 0.5rem; font-weight: 500; cursor: pointer;
            transition: opacity 0.2s;
        }
        .execute-btn:hover:not(:disabled) { opacity: 0.9; }
        .execute-btn:disabled { opacity: 0.5; cursor: not-allowed; }

        /* Result */
        .result {
            padding: 0.75rem; border-radius: 0.5rem; font-family: monospace;
            font-size: 0.875rem; white-space: pre-wrap; word-break: break-word;
        }
        .result-success { background: #dcfce7; border: 1px solid #86efac; color: #166534; }
        .result-error { background: #fee2e2; border: 1px solid #fca5a5; color: #991b1b; }

        /* Status */
        .status { display: flex; align-items: center; gap: 0.5rem; font-size: 0.75rem; color: #6b7280; }
        .status-indicator { width: 0.5rem; height: 0.5rem; border-radius: 50%; background: #d1d5db; }
        .status-indicator.success { background: #22c55e; }
        .status-indicator.error { background: #ef4444; }
        .status-indicator.loading { background: #eab308; }
    `;

    constructor() {
        super();
        this.funcName = '';
        this.funcInfo = null;
        this.params = {};
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

        // Load funcInfo from registry if not already set
        if (this.funcName && !this.funcInfo) {
            try {
                const schemas = await this._client.loadSchemas();
                const info = schemas[this.funcName];
                if (!info) throw new Error(`Function "${this.funcName}" not found in registry`);
                this.funcInfo = info;
            } catch (error) {
                this._errorMessage = error.message;
                this._setStatus('error', 'Error loading function');
            }
        }

        // Initialize params with defaults if funcInfo is already available
        if (this.funcInfo && Object.keys(this.params).length === 0) {
            this._initParamsWithDefaults();
        }

        this.dispatchEvent(new CustomEvent('function-connected', {
            detail: { funcName: this.funcName, funcInfo: this.funcInfo },
            bubbles: true,
            composed: true
        }));
    }

    // Re-initialize defaults when funcInfo changes
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
    // STATE MANAGEMENT
    // ========================================================================

    setParam(name, value) {
        this.params = { ...this.params, [name]: value };

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

    // ========================================================================
    // EXECUTION
    // ========================================================================

    /**
     * Validates and executes the function with the current parameters.
     * Unwraps the envelope: { result, success, message, ... } → result.
     *
     * @fires before-execute
     * @fires after-execute
     * @fires execute-error
     * @returns {Promise<any>} The unwrapped payload.
     */
    async execute() {
        // 1. Validate params against funcInfo
        if (!this.validate()) {
            this._errorMessage = 'Please fill all required fields and fix errors.';
            this._setStatus('error', 'Validation error');
            return;
        }

        // 2. Pre-execution hook (cancellable)
        const preEvent = new CustomEvent('before-execute', {
            detail: { funcName: this.funcName, params: this.params },
            bubbles: true,
            composed: true,
            cancelable: true
        });
        if (!this.dispatchEvent(preEvent)) return;

        // 3. Setup execution state
        this._isExecuting = true;
        this._setStatus('loading', 'Executing...');
        this._errorMessage = '';

        try {
            // 4. Call API
            const data = await this._client.call(this.funcName, this.params, this.funcInfo);

            // Store full envelope
            this.envelope = data;

            // Unwrap payload
            const hasEnvelopeShape = (
                data && typeof data === 'object' &&
                Object.prototype.hasOwnProperty.call(data, 'result')
            );
            this.result = hasEnvelopeShape ? data.result : data;

            if (data && typeof data === 'object') {
                this.success = data.success;
                this.message = data.message;
            } else {
                this.success = undefined;
                this.message = '';
            }

            if (this.success === false) {
                this._errorMessage = this.message || 'Execution error';
                this._setStatus('error', 'Execution error');
            } else {
                this._errorMessage = '';
                this._setStatus('success', 'Executed successfully');
            }

            this.dispatchEvent(new CustomEvent('after-execute', {
                detail: { funcName: this.funcName, params: this.params, result: this.result, envelope: this.envelope },
                bubbles: true,
                composed: true
            }));

            return this.result;
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
     * Validates current params against funcInfo using RefractClient.validate().
     * Updates this.errors reactively.
     * @returns {boolean} Whether all params are valid.
     */
    validate() {
        const { isValid, errors } = RefractClient.validate(this.params, this.funcInfo);
        this.errors = errors;
        return isValid;
    }

    // ========================================================================
    // INTERNAL HELPERS
    // ========================================================================

    _isComplexType(type) {
        if (!type) return false;
        return /\b(dict|list)\b|json/i.test(type);
    }

    _setStatus(type, message) {
        this._status = type;
        this._statusMessage = message;
    }

    // ========================================================================
    // RENDERING
    // ========================================================================

    render() {
        if (!this.funcInfo) {
            return html`<div class="container">Loading...</div>`;
        }

        return html`
            <div class="container">
                <div class="header">
                    <div class="header-row">
                        <h3 class="title">🔧 ${this.funcInfo.name}</h3>
                    </div>
                    ${this.funcInfo.description ? html`<p class="description">${this.funcInfo.description}</p>` : ''}
                </div>

                ${this._errorMessage ? html`<div class="error-banner">${this._errorMessage}</div>` : ''}

                ${this.funcInfo.parameters?.length ? html`
                    <div class="params">
                        ${this.funcInfo.parameters.map(p => this.renderParam(p))}
                    </div>
                ` : ''}

                <button class="execute-btn" ?disabled=${this._isExecuting} @click=${this.execute}>
                    ${this._isExecuting ? 'Executing...' : `Execute ⚡`}
                </button>

                ${this.result !== null ? this.renderResult() : ''}

                <div class="status">
                    <div class="status-indicator ${this._status}"></div>
                    <span>${this._statusMessage}</span>
                </div>
            </div>
        `;
    }

    renderParam(param) {
        const hasError = this.errors[param.name];
        const errorClass = hasError ? 'error' : '';
        const currentValue = this.params[param.name] ?? '';

        let inputHtml;

        if (param.choices?.length > 0) {
            inputHtml = html`
                <select name="${param.name}" class="${errorClass}" ?required=${param.required}
                    @change=${e => this.setParam(param.name, e.target.value)}>
                    ${param.choices.map(c => html`<option value="${c}" ?selected=${c === currentValue}>${c}</option>`)}
                </select>
            `;
        } else if (this._isComplexType(param.type)) {
            const displayValue = typeof currentValue === 'object' ? JSON.stringify(currentValue, null, 2) : currentValue;
            inputHtml = html`
                <textarea name="${param.name}" class="${errorClass}" rows="3" .value=${displayValue}
                    ?required=${param.required}
                    @change=${e => this.setParam(param.name, e.target.value)}></textarea>
            `;
        } else if (param.type === 'bool') {
            inputHtml = html`
                <div class="checkbox-wrapper">
                    <input type="checkbox" name="${param.name}" ?checked=${!!currentValue}
                        @change=${e => this.setParam(param.name, e.target.checked)}>
                    <span>Enable</span>
                </div>
            `;
        } else {
            const isNumber = param.type === 'int' || param.type === 'float';
            inputHtml = html`
                <input type="${isNumber ? 'number' : 'text'}" name="${param.name}" class="${errorClass}"
                    .value=${String(currentValue)} ?required=${param.required}
                    step="${param.type === 'float' ? 'any' : param.type === 'int' ? '1' : ''}"
                    @change=${e => this.setParam(param.name, e.target.value)}>
            `;
        }

        return html`
            <div class="param-group">
                <label class="param-label">
                    ${param.name} ${param.required ? html`<span class="param-required">*</span>` : ''}
                </label>
                <p class="param-desc">${param.description} (${param.type})</p>
                ${inputHtml}
                ${hasError ? html`<span class="field-error">${this.errors[param.name]}</span>` : ''}
            </div>
        `;
    }

    renderResult() {
        const isError = this.result?._isError;
        const content = typeof this.result === 'object' && !isError
            ? JSON.stringify(this.result, null, 2)
            : this.result?._message || this.result;

        return html`
            <div class="result ${isError ? 'result-error' : 'result-success'}">
                ${content}
            </div>
        `;
    }
}

// Register custom element
if (!customElements.get('auto-function-element')) {
    customElements.define('auto-function-element', AutoFunctionElement);
}
