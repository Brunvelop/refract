/**
 * generator.js
 * Generador automático de Custom Elements para funciones del registry de Refract.
 *
 * Auto-consulta /functions/details y registra un custom element por cada función.
 * Elemento generado: <auto-{funcName}> → instancia de AutoFunctionElement con
 * funcName y funcInfo ya inyectados.
 *
 * Se inicializa automáticamente al cargar el script.
 */

import { AutoFunctionElement } from './element.js';

/**
 * GENERADOR DINÁMICO
 * Fábrica que crea y registra custom elements basados en AutoFunctionElement.
 */
export class AutoElementGenerator {
    constructor() {
        this.functions = {};
        this.registeredElements = new Set();
    }

    async init() {
        try {
            await this.loadFunctions();
            this.generateAllElements();
            console.log(`✅ ${this.registeredElements.size} custom elements generados`);
        } catch (error) {
            console.error('❌ Error inicializando auto-element-generator:', error);
            throw error;
        }
    }

    async loadFunctions() {
        const response = await fetch('/functions/details');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        this.functions = data.functions;
    }

    generateAllElements() {
        for (const [funcName, funcInfo] of Object.entries(this.functions)) {
            this.generateElement(funcName, funcInfo);
        }
    }

    generateElement(funcName, funcInfo) {
        const elementName = `auto-${funcName.replace(/_/g, '-')}`;
        if (customElements.get(elementName)) return;

        // Extendemos de AutoFunctionElement (que extiende del Controller)
        const ElementClass = class extends AutoFunctionElement {
            constructor() {
                super();
                this.funcName = funcName;
                this.funcInfo = funcInfo;
            }
        };

        customElements.define(elementName, ElementClass);
        this.registeredElements.add(elementName);
    }
}

// Inicialización automática
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', async () => {
        window.autoElementGenerator = new AutoElementGenerator();
        await window.autoElementGenerator.init();
    });
} else {
    window.autoElementGenerator = new AutoElementGenerator();
    window.autoElementGenerator.init();
}
