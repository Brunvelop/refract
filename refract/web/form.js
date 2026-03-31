/**
 * form.js
 * High-level form management for Refract functions.
 *
 * Exports:
 *   - RefractForm        — stateful form controller (extends EventTarget)
 *   - createParamInput   — DOM utility to generate input elements from ParamSchema
 *
 * Vanilla JS — no framework dependency. Works in any context:
 * plain scripts, React refs, Vue refs, Lit components, etc.
 *
 * Usage:
 *   import { RefractForm, createParamInput } from '/refract/form.js';
 */

import { RefractClient } from './client.js';

// =============================================================================
// RefractForm
// =============================================================================

/**
 * Stateful form controller for one or more Refract functions.
 * Extends EventTarget — listen with form.addEventListener(event, handler).
 *
 * Events emitted:
 *   load         — schemas loaded             detail: { functions: FunctionSchema[] }
 *   change       — any state change           detail: { params, errors, selected }
 *   select       — function selected          detail: FunctionSchema
 *   submit-start — submit began               (no detail)
 *   stream       — SSE token received         detail: { event: string, data: any }
 *   result       — successful response        detail: any
 *   error        — error occurred             detail: Error
 *   submit-end   — submit finished (always)   (no detail)
 *
 * @example
 * // Auto-select a single function and submit
 * const form = new RefractForm({ function: 'generate_image' });
 * await form.ready;
 * form.set('prompt', 'a cat in space');
 * const result = await form.submit();
 *
 * @example
 * // Filter by tag, handle events
 * const form = new RefractForm({ tag: 'generators' });
 * form.addEventListener('load', ({ detail }) => renderFunctionList(detail.functions));
 * form.addEventListener('change', ({ detail }) => renderInputs(detail));
 * form.addEventListener('result', ({ detail }) => showOutput(detail));
 */
export class RefractForm extends EventTarget {
    /**
     * @param {object} [options]
     * @param {string} [options.function]       Filter & auto-select a specific function by name
     * @param {string} [options.tag]            Filter functions to those with this tag
     * @param {RefractClient} [options.client]  Provide an existing RefractClient (optional)
     */
    constructor({ function: funcName, tag, client } = {}) {
        super();
        this._client = client ?? new RefractClient();
        this._funcFilter = funcName ?? null;
        this._tagFilter  = tag ?? null;

        // ── State ──────────────────────────────────────────────────────────
        /** @type {object[]} */            this._functions      = [];
        /** @type {object|null} */         this._selected       = null;
        /** @type {object} */              this._params         = {};
        /** @type {Object.<string,string>} */ this._errors      = {};
        /** @type {boolean} */             this._isLoading      = false;
        /** @type {boolean} */             this._isSubmitting   = false;
        /** @type {AbortController|null} */ this._abortController = null;

        // Kick off schema loading immediately
        this._initReady();
    }

    // =========================================================================
    // Getters
    // =========================================================================

    /** @returns {object[]} Loaded function schemas (copy) */
    get functions()    { return [...this._functions]; }

    /** @returns {object|null} Currently selected FunctionSchema */
    get selected()     { return this._selected; }

    /** @returns {object} Current param values (shallow copy) */
    get params()       { return { ...this._params }; }

    /** @returns {Object.<string,string>} Current validation errors (shallow copy) */
    get errors()       { return { ...this._errors }; }

    /** @returns {boolean} True while schemas are being fetched */
    get isLoading()    { return this._isLoading; }

    /** @returns {boolean} True while a submit() is in flight */
    get isSubmitting() { return this._isSubmitting; }

    // =========================================================================
    // Actions
    // =========================================================================

    /**
     * Selects a function by name. Resets params to their defaults and clears errors.
     * Emits: select, change
     *
     * @param {string} funcName
     * @throws {Error} If the function is not found (await form.ready first)
     */
    select(funcName) {
        const fn = this._functions.find(f => f.name === funcName);
        if (!fn) throw new Error(`Function "${funcName}" not found. Did you await form.ready?`);
        this._applySelect(fn);
    }

    /**
     * Updates a single parameter value. Does NOT validate.
     * Emits: change
     *
     * @param {string} name  Parameter name
     * @param {*}      value New value (must match the Python type — no coercion)
     */
    set(name, value) {
        this._params = { ...this._params, [name]: value };
        this.dispatchEvent(new CustomEvent('change', { detail: this._snapshot() }));
    }

    /**
     * Batch-update parameter values in a single change event.
     * Accepts either a plain object or a callback.
     * Emits: change (once)
     *
     * @param {object|function} objOrFn
     *   - object   → merged into current params  e.g. { prompt: 'x', size: '512' }
     *   - function → receives prev params copy, must return new params object
     *
     * @example
     * form.setMany({ prompt: 'a cat', size: '512x512' });
     * form.setMany(prev => ({ ...prev, prompt: prev.prompt + '!' }));
     */
    setMany(objOrFn) {
        if (typeof objOrFn === 'function') {
            this._params = objOrFn({ ...this._params });
        } else {
            this._params = { ...this._params, ...objOrFn };
        }
        this.dispatchEvent(new CustomEvent('change', { detail: this._snapshot() }));
    }

    /**
     * Validates all current params against the selected function's schema.
     * Populates form.errors. Does NOT submit.
     * Emits: change
     *
     * @returns {{ valid: boolean, errors: Object.<string,string> }}
     * @throws {Error} If no function is selected
     */
    validate() {
        if (!this._selected) throw new Error('No function selected');
        const { valid, errors } = this._client._validateParams(this._params, this._selected);
        this._errors = errors;
        this.dispatchEvent(new CustomEvent('change', { detail: this._snapshot() }));
        return { valid, errors: { ...errors } };
    }

    /**
     * Validates params, then submits the selected function.
     *
     * - Non-streaming functions: uses client.call(), emits result
     * - Streaming functions: uses client.stream(), emits each stream token and
     *   a final result with the last received data
     *
     * Both returns the result AND emits events — use whichever pattern fits.
     *
     * Emits: submit-start, [stream…], result | error, submit-end
     *
     * @returns {Promise<any>} The function result (your Pydantic model as JSON)
     * @throws {Error} If validation fails or the server call errors
     */
    async submit() {
        if (!this._selected) throw new Error('No function selected');

        // Validate before sending
        const { valid, errors } = this.validate();
        if (!valid) {
            const msg = Object.entries(errors).map(([k, v]) => `${k}: ${v}`).join(', ');
            const err  = Object.assign(new Error(`Validation failed — ${msg}`), { errors });
            this.dispatchEvent(new CustomEvent('error', { detail: err }));
            throw err;
        }

        this._isSubmitting    = true;
        this._abortController = new AbortController();
        this.dispatchEvent(new CustomEvent('submit-start'));

        try {
            const funcName = this._selected.name;
            const params   = { ...this._params };
            let result;

            if (this._selected.streaming) {
                let lastData = null;
                for await (const { event, data } of this._client.stream(funcName, params, {
                    signal: this._abortController.signal,
                })) {
                    this.dispatchEvent(new CustomEvent('stream', { detail: { event, data } }));
                    lastData = data;
                }
                result = lastData;
            } else {
                result = await this._client.call(funcName, params);
            }

            this.dispatchEvent(new CustomEvent('result', { detail: result }));
            return result;

        } catch (err) {
            if (err.name === 'AbortError') {
                // Cancelled via abort() — swallow silently
                return;
            }
            this.dispatchEvent(new CustomEvent('error', { detail: err }));
            throw err;

        } finally {
            this._isSubmitting    = false;
            this._abortController = null;
            this.dispatchEvent(new CustomEvent('submit-end'));
        }
    }

    /**
     * Resets params to the defaults of the currently selected function.
     * Clears validation errors.
     * Emits: change
     */
    reset() {
        if (!this._selected) return;
        this._params = this._defaultParams(this._selected);
        this._errors = {};
        this.dispatchEvent(new CustomEvent('change', { detail: this._snapshot() }));
    }

    /**
     * Cancels an in-progress submit() call.
     * The submit() Promise resolves (not rejects) with undefined after abort.
     * submit-end is still emitted.
     */
    abort() {
        this._abortController?.abort();
    }

    /**
     * Retries schema loading (e.g. after a network failure).
     * Resets all state and creates a fresh `this.ready` Promise.
     */
    reload() {
        this._functions = [];
        this._selected  = null;
        this._params    = {};
        this._errors    = {};
        this._initReady();
    }

    // =========================================================================
    // Private helpers
    // =========================================================================

    /**
     * Kicks off schema loading and wires up `this.ready`.
     * @private
     */
    _initReady() {
        this._isLoading = true;
        this.ready = new Promise((resolve, reject) => {
            this._client.loadSchemas()
                .then(schemas => {
                    let functions = Object.values(schemas);

                    if (this._funcFilter) {
                        functions = functions.filter(f => f.name === this._funcFilter);
                    }
                    if (this._tagFilter) {
                        functions = functions.filter(f => f.tags?.includes(this._tagFilter));
                    }

                    this._functions = functions;
                    this._isLoading = false;

                    // Auto-select when exactly one function matches
                    if (functions.length === 1) {
                        this._applySelect(functions[0]);
                    }

                    this.dispatchEvent(new CustomEvent('load', { detail: { functions: [...functions] } }));
                    resolve(functions);
                })
                .catch(err => {
                    this._isLoading = false;
                    this.dispatchEvent(new CustomEvent('error', { detail: err }));
                    reject(err);
                });
        });
    }

    /**
     * Applies a function selection: updates state and emits select + change.
     * @private
     */
    _applySelect(fn) {
        this._selected = fn;
        this._params   = this._defaultParams(fn);
        this._errors   = {};
        this.dispatchEvent(new CustomEvent('select', { detail: fn }));
        this.dispatchEvent(new CustomEvent('change', { detail: this._snapshot() }));
    }

    /**
     * Builds the initial params object from a function schema's defaults.
     * - Uses the declared default if non-null
     * - Bool params without default → false
     * - Literal params without default → first choice
     * - Everything else → undefined (required check will catch it on validate)
     * @private
     */
    _defaultParams(fn) {
        const params = {};
        for (const p of (fn.parameters ?? [])) {
            if (p.default !== null && p.default !== undefined) {
                params[p.name] = p.default;
            } else if (p.type === 'bool') {
                params[p.name] = false;
            } else if (Array.isArray(p.choices) && p.choices.length > 0) {
                params[p.name] = p.choices[0];
            } else {
                params[p.name] = undefined;
            }
        }
        return params;
    }

    /** @private */
    _snapshot() {
        return {
            params:   { ...this._params },
            errors:   { ...this._errors },
            selected: this._selected,
        };
    }
}

// =============================================================================
// createParamInput
// =============================================================================

/**
 * Creates a DOM input element for a single ParamSchema.
 *
 * Two overloads:
 *
 *   // Recommended — auto-binds to a RefractForm
 *   createParamInput(param, form)
 *   // Reads initial value from form.params[param.name]
 *   // Calls form.set(param.name, value) on every change
 *
 *   // Manual — full control
 *   createParamInput(param, { value, onChange })
 *   // Sets element to `value`, calls onChange(newValue) on change
 *
 * All elements receive:
 *   - CSS class:  rf-input | rf-select | rf-textarea | rf-checkbox
 *   - Attribute:  data-rf-param="{name}"  data-rf-type="{type}"
 *   - No inline styles — apply CSS as you like
 *
 * Type → element mapping:
 *   bool          → <input type="checkbox">
 *   int           → <input type="number" step="1">
 *   float         → <input type="number" step="0.1">
 *   Literal[...]  → <select>          (choices array)
 *   str (long)    → <textarea>        (name matches TEXTAREA_KEYWORDS)
 *   str (short)   → <input type="text">
 *   default       → <input type="text">
 *
 * @param {object} param                           ParamSchema object
 * @param {string} param.name                      Parameter name
 * @param {string} param.type                      Serialized Python type ('str', 'int', 'bool', ...)
 * @param {*}      [param.default]                 Default value
 * @param {boolean} param.required                 Whether the param is required
 * @param {string} [param.description]             Human-readable description
 * @param {any[]}  [param.choices]                 Available choices (from Literal types)
 *
 * @param {RefractForm|{ value: any, onChange: function }} formOrOptions
 *   Pass a RefractForm for auto-binding, or { value, onChange } for manual control.
 *
 * @returns {HTMLElement}
 *
 * @example
 * // Auto-bind
 * const form = new RefractForm({ function: 'generate_image' });
 * await form.ready;
 * for (const param of form.selected.parameters) {
 *     container.appendChild(createParamInput(param, form));
 * }
 *
 * @example
 * // Manual
 * const input = createParamInput(param, {
 *     value: 'hello',
 *     onChange: v => console.log('changed:', v),
 * });
 */
export function createParamInput(param, formOrOptions) {
    // ── Resolve overload ────────────────────────────────────────────────────
    const isFormBind = formOrOptions != null && typeof formOrOptions.set === 'function';
    let initialValue, onChange;

    if (isFormBind) {
        initialValue = formOrOptions.params[param.name];
        onChange = (value) => formOrOptions.set(param.name, value);
    } else {
        initialValue = formOrOptions?.value;
        onChange     = formOrOptions?.onChange ?? (() => {});
    }

    // ── Detect element type ─────────────────────────────────────────────────
    const hasChoices = Array.isArray(param.choices) && param.choices.length > 0;
    const baseType   = (param.type ?? 'str').replace(/\?$/, '');   // strip Optional '?'

    let element;

    if (hasChoices) {
        element = _buildSelect(param, initialValue, onChange);
    } else if (baseType === 'bool') {
        element = _buildCheckbox(param, initialValue, onChange);
    } else if (baseType === 'int' || baseType === 'float') {
        element = _buildNumber(param, baseType, initialValue, onChange);
    } else if (_isTextareaParam(param)) {
        element = _buildTextarea(param, initialValue, onChange);
    } else {
        element = _buildText(param, initialValue, onChange);
    }

    // ── Common data attributes ──────────────────────────────────────────────
    element.dataset.rfParam = param.name;
    element.dataset.rfType  = param.type ?? 'str';

    return element;
}

// =============================================================================
// createParamInput — private builders
// =============================================================================

/**
 * Names that suggest the field should be a <textarea> rather than <input>.
 * Checked against param.name (case-insensitive, substring match).
 */
const TEXTAREA_KEYWORDS = [
    'prompt', 'description', 'instructions', 'text',
    'content', 'message', 'body', 'caption', 'summary', 'notes',
];

function _isTextareaParam(param) {
    const name = param.name.toLowerCase();
    return TEXTAREA_KEYWORDS.some(kw => name === kw || name.includes(kw));
}

/**
 * <select> for Literal / choices params.
 * @private
 */
function _buildSelect(param, value, onChange) {
    const el = document.createElement('select');
    el.classList.add('rf-select');
    if (param.required) el.required = true;

    for (const choice of param.choices) {
        const opt = document.createElement('option');
        opt.value       = String(choice);
        opt.textContent = String(choice);
        el.appendChild(opt);
    }

    // Set initial value (fall back to first choice)
    el.value = String(value ?? param.choices[0] ?? '');

    el.addEventListener('change', () => {
        // Coerce back to original type: if choices are numbers, return a number
        const raw     = el.value;
        const coerced = typeof param.choices[0] === 'number' ? Number(raw) : raw;
        onChange(coerced);
    });

    return el;
}

/**
 * <input type="checkbox"> for bool params.
 * @private
 */
function _buildCheckbox(param, value, onChange) {
    const el = document.createElement('input');
    el.type = 'checkbox';
    el.classList.add('rf-input', 'rf-checkbox');

    el.checked = Boolean(value ?? param.default ?? false);

    el.addEventListener('change', () => onChange(el.checked));

    return el;
}

/**
 * <input type="number"> for int / float params.
 * @private
 */
function _buildNumber(param, baseType, value, onChange) {
    const el  = document.createElement('input');
    el.type   = 'number';
    el.step   = baseType === 'int' ? '1' : '0.1';
    el.classList.add('rf-input');
    if (param.required) el.required = true;

    _applyPlaceholder(el, param);

    if (value !== undefined && value !== null) {
        el.value = String(value);
    }

    el.addEventListener('input', () => {
        if (el.value === '') {
            onChange(undefined);
        } else {
            onChange(baseType === 'int' ? parseInt(el.value, 10) : parseFloat(el.value));
        }
    });

    return el;
}

/**
 * <textarea> for long-text params (prompt, description, …).
 * @private
 */
function _buildTextarea(param, value, onChange) {
    const el = document.createElement('textarea');
    el.classList.add('rf-input', 'rf-textarea');
    if (param.required) el.required = true;

    _applyPlaceholder(el, param);

    el.value = value ?? '';

    el.addEventListener('input', () => onChange(el.value));

    return el;
}

/**
 * <input type="text"> for str and unknown types.
 * @private
 */
function _buildText(param, value, onChange) {
    const el  = document.createElement('input');
    el.type   = 'text';
    el.classList.add('rf-input');
    if (param.required) el.required = true;

    _applyPlaceholder(el, param);

    el.value = value ?? '';

    el.addEventListener('input', () => onChange(el.value));

    return el;
}

/**
 * Sets placeholder text on an element:
 *   - Required param with no default → "Required"
 *   - Optional param with a default  → "default: {value}"
 * @private
 */
function _applyPlaceholder(el, param) {
    if (param.required && (param.default === null || param.default === undefined)) {
        el.placeholder = 'Required';
    } else if (param.default !== null && param.default !== undefined) {
        el.placeholder = `default: ${param.default}`;
    }
}
