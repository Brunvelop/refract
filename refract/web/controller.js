/**
 * controller.js
 * Controlador base con lógica pura para elementos de función de Refract.
 *
 * CAPA 2: LitElement con estado, validación y comunicación con la API.
 * Desacoplado de la presentación visual.
 *
 * Responsabilidades:
 * - Gestionar el estado de parámetros, resultado y ejecución
 * - Validar parámetros contra el schema (funcInfo)
 * - Delegar las llamadas HTTP/SSE a RefractClient (Capa 1)
 * - Emitir custom events para el ciclo de vida de ejecución
 */

import { LitElement, html } from 'https://cdn.jsdelivr.net/gh/lit/dist@3/core/lit-core.min.js';
import { RefractClient } from './client.js';

/**
 * CONTROLADOR BASE (LÓGICA PURA)
 * Maneja el estado, la validación y la comunicación con la API.
 * Desacoplado de la presentación visual.
 */
export class AutoFunctionController extends LitElement {
    static properties = {
        // Configuración
        funcName: { type: String, attribute: 'func-name' },
        funcInfo: { type: Object, state: true },

        // Estado
        params: { type: Object, state: true }, // Valores actuales de los parámetros
        result: { type: Object, state: true },
        // Respuesta completa del backend (envelope)
        envelope: { type: Object, state: true },
        // Metadata conveniente (derivada del envelope)
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

        // Capa 1: cliente HTTP puro (sin Lit)
        this._client = new RefractClient();
    }

    async connectedCallback() {
        super.connectedCallback();

        // 1. Si tengo nombre pero no info, cargarla del registry
        if (this.funcName && !this.funcInfo) {
            try {
                await this.loadFunctionInfo();
            } catch (error) {
                this._errorMessage = error.message;
                this._setStatus('error', 'Error loading function');
            }
        }

        // 2. Inicializar params con defaults si funcInfo ya está cargado
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

    // Si funcInfo cambia, reinicializar defaults
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
     * Establece el valor de un parámetro y actualiza el estado.
     */
    setParam(name, value) {
        // Actualización inmutable para disparar reactividad de Lit
        this.params = {
            ...this.params,
            [name]: value
        };

        // Limpiar error asociado si existe
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
     * Devuelve el envelope completo del backend.
     * Útil para consumidores que necesiten metadata (reasoning/trajectory/history, etc.).
     */
    getEnvelope() {
        return this.envelope;
    }

    /**
     * Devuelve el payload real (alias de result).
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

    async execute() {
        // 1. Validar estado (params vs funcInfo)
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

            // Guardar envelope completo
            this.envelope = data;

            // Derivar metadata + payload estandarizado
            const hasEnvelopeShape = (data && typeof data === 'object' && Object.prototype.hasOwnProperty.call(data, 'result'));
            this.result = hasEnvelopeShape ? data.result : data;

            if (data && typeof data === 'object') {
                this.success = data.success;
                this.message = data.message;
            } else {
                this.success = undefined;
                this.message = '';
            }

            // Si el backend devuelve success=false, lo tratamos como ejecución fallida
            // (pero NO lanzamos excepción: queda a criterio del consumidor)
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
     * Valida los parámetros actuales contra la definición (funcInfo).
     * NO depende del DOM.
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
                    // Si es string (desde textarea), intentar parsear
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
     * Procesa parámetros aplicando conversiones de tipo según la definición de funcInfo.
     * Delega a RefractClient._processParams(); mantiene this.funcInfo como fallback.
     * @param {object} params - Parámetros crudos
     * @param {object|null} funcInfoOverride - FuncInfo alternativo (para streaming con otra función)
     * @returns {object} Parámetros procesados con tipos correctos
     */
    _processParams(params, funcInfoOverride = null) {
        return this._client._processParams(params, funcInfoOverride || this.funcInfo);
    }

    async callAPI(params) {
        return this._client.call(this.funcName, params, this.funcInfo);
    }

    /**
     * Async generator que consume un endpoint SSE y produce eventos parseados.
     * Delega a RefractClient.stream().
     * @param {string} endpoint - Nombre del endpoint (se usa como URL: /{endpoint})
     * @param {object} params - Parámetros a enviar como JSON body
     * @param {object|null} funcInfo - FuncInfo para procesamiento de tipos (opcional)
     * @yields {{ event: string, data: object|string }} Eventos SSE parseados
     */
    async *callStreamAPI(endpoint, params, funcInfo = null, options = {}) {
        yield* this._client.stream(endpoint, params, funcInfo || this.funcInfo, options);
    }

    /**
     * Helper estático para ejecutar funciones sin crear elementos en el DOM.
     * Útil para llamadas inter-funciones (ej: chat llamando a calculate_context_usage).
     *
     * @param {string} funcName - Nombre de la función registrada
     * @param {object} params - Parámetros para la función
     * @returns {Promise<any>} - Resultado de la ejecución
     * @throws {Error} - Si la función no existe o falla la ejecución
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

            // Misma lógica de unwrap que execute(): extraer payload del envelope
            const hasEnvelopeShape = (data && typeof data === 'object' && Object.prototype.hasOwnProperty.call(data, 'result'));
            return hasEnvelopeShape ? data.result : data;
        } catch (error) {
            console.error(`❌ Error executing function "${funcName}":`, error);
            throw error;
        }
    }

    // Helpers internos
    _isComplexType(type) {
        if (!type) return false;
        return /\b(dict|list)\b|json/i.test(type);
    }

    _setStatus(type, message) {
        this._status = type;
        this._statusMessage = message;
    }

    // Default render: nada visual, solo slot
    render() {
        return html`<slot></slot>`;
    }
}

// Registrar custom element
if (!customElements.get('auto-function-controller')) {
    customElements.define('auto-function-controller', AutoFunctionController);
}
