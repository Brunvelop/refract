/**
 * element.js
 * UI genérica tipo "Tarjeta" para funciones del registry de Refract.
 *
 * CAPA 3: Extiende AutoFunctionController con presentación visual.
 * Usa Shadow DOM. NO DISEÑADA PARA SER EXTENDIDA.
 *
 * Responsabilidades:
 * - Renderizar formularios automáticos basados en el schema (funcInfo)
 * - Mostrar resultados y estados de ejecución
 * - Adaptar el tipo de input según el tipo de parámetro
 */

import { css, html } from 'https://cdn.jsdelivr.net/gh/lit/dist@3/core/lit-core.min.js';
import { AutoFunctionController } from './controller.js';

/**
 * UI GENÉRICA (TARJETA)
 * Implementación visual estándar de AutoFunctionController.
 * Usa Shadow DOM.
 * NO DISEÑADA PARA SER EXTENDIDA.
 */
export class AutoFunctionElement extends AutoFunctionController {
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

// Registrar custom element
if (!customElements.get('auto-function-element')) {
    customElements.define('auto-function-element', AutoFunctionElement);
}
