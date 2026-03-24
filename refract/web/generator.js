/**
 * generator.js
 * Automatic Custom Element generator for functions in the Refract registry.
 *
 * Auto-queries /functions/details and registers one custom element per function.
 * Generated element: <auto-{funcName}> → instance of AutoFunctionElement with
 * funcName and funcInfo already injected.
 *
 * Initializes automatically when the script is loaded.
 */

import { AutoFunctionElement } from './element.js';

/**
 * DYNAMIC GENERATOR
 * Factory that creates and registers custom elements based on AutoFunctionElement.
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
            console.log(`✅ ${this.registeredElements.size} custom elements generated`);
        } catch (error) {
            console.error('❌ Error initializing auto-element-generator:', error);
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

        // Extend AutoFunctionElement (which extends the Controller)
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

// Automatic initialization
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', async () => {
        window.autoElementGenerator = new AutoElementGenerator();
        await window.autoElementGenerator.init();
    });
} else {
    window.autoElementGenerator = new AutoElementGenerator();
    window.autoElementGenerator.init();
}
