/**
 * client.js
 * Cliente HTTP puro para interactuar con el registry de Refract.
 *
 * CAPA 1: Vanilla JS, sin dependencia de Lit ni del DOM.
 * Puede usarse en cualquier contexto (componentes Lit, vanilla JS, tests, etc.).
 *
 * Responsabilidades:
 * - Cargar schemas del registry  (/functions/details)
 * - Realizar llamadas HTTP (GET/POST) a funciones registradas
 * - Consumir streams SSE como async generators
 * - Procesar/coercionar tipos de parámetros según el schema
 */
export class RefractClient {
    constructor() {
        /** @type {Object.<string, Object>|null} Schemas cargados desde /functions/details */
        this._schemas = null;
    }

    // ========================================================================
    // SCHEMA MANAGEMENT
    // ========================================================================

    /**
     * Carga todos los schemas del registry desde /functions/details.
     * El resultado se cachea en this._schemas.
     *
     * @returns {Promise<Object.<string, Object>>} Mapa funcName → funcInfo
     */
    async loadSchemas() {
        const response = await fetch('/functions/details');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        this._schemas = data.functions;
        return this._schemas;
    }

    /**
     * Obtiene el schema (funcInfo) de una función concreta.
     * Requiere haber llamado loadSchemas() previamente, o devuelve null.
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
     * Ejecuta una llamada HTTP a una función registrada.
     * Soporta GET y POST según el http_methods del schema.
     * Retorna la respuesta raw del servidor (el "envelope").
     *
     * @param {string} funcName - Nombre de la función registrada
     * @param {object} params - Parámetros para la función
     * @param {object|null} funcInfo - Schema de la función (opcional; si no se pasa, se carga automáticamente)
     * @returns {Promise<any>} Respuesta JSON del servidor
     */
    async call(funcName, params, funcInfo = null) {
        let info = funcInfo || this.getSchema(funcName);

        // Auto-cargar schemas si no disponibles
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
     * Async generator que consume un endpoint SSE y produce eventos parseados.
     *
     * @param {string} endpoint - Nombre del endpoint (URL: /{endpoint})
     * @param {object} params - Parámetros a enviar como JSON body
     * @param {object|null} funcInfo - FuncInfo para procesamiento de tipos (opcional)
     * @param {object} options - Opciones adicionales (e.g. { signal: AbortSignal })
     * @yields {{ event: string, data: object|string }} Eventos SSE parseados
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

        // Procesar contenido restante del buffer tras fin de stream
        if (buffer) {
            if (buffer.startsWith('event: ')) {
                currentEvent = buffer.slice(7).trim();
            } else if (buffer.startsWith('data: ')) {
                currentData = buffer.slice(6);
            }
        }

        // Evento pendiente si stream termina sin \n\n final
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
     * Procesa parámetros aplicando conversiones de tipo según el schema (funcInfo).
     * Convierte strings a JSON para tipos complejos (dict/list), int, float.
     *
     * @param {object} params - Parámetros crudos
     * @param {object|null} funcInfo - Schema de la función (para conocer tipos)
     * @returns {object} Parámetros con tipos correctos
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
     * Determina si un tipo de parámetro es complejo (dict, list, JSON).
     *
     * @param {string|null} type
     * @returns {boolean}
     */
    _isComplexType(type) {
        if (!type) return false;
        return /\b(dict|list)\b|json/i.test(type);
    }
}
