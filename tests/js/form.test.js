/**
 * tests/js/form.test.js
 * Unit tests for RefractForm and createParamInput (refract/web/form.js).
 *
 * Run with:  npm run test:js
 */

import { describe, it, expect, vi } from 'vitest';
import { RefractForm, createParamInput } from '../../refract/web/form.js';

// =============================================================================
// Fixtures
// =============================================================================

const GREET_SCHEMA = {
    name: 'greet',
    description: 'Greet someone',
    http_methods: ['POST'],
    interfaces: ['api'],
    streaming: false,
    tags: ['utility'],
    parameters: [
        { name: 'name',  type: 'str', default: null, required: true,  description: 'Name',  choices: null },
        { name: 'count', type: 'int', default: 1,    required: false, description: 'Count', choices: null },
    ],
};

const STREAM_SCHEMA = {
    ...GREET_SCHEMA,
    name: 'stream_greet',
    streaming: true,
};

const IMAGE_SCHEMA = {
    name: 'generate_image',
    description: 'Generate image',
    http_methods: ['POST'],
    interfaces: ['api'],
    streaming: false,
    tags: ['image', 'generators'],
    parameters: [
        { name: 'prompt', type: 'str',                      default: null,  required: true,  description: 'Prompt',   choices: null },
        { name: 'size',   type: "Literal['512', '1024']",   default: '512', required: false, description: 'Size',     choices: ['512', '1024'] },
        { name: 'hd',     type: 'bool',                     default: false, required: false, description: 'HD mode',  choices: null },
        { name: 'steps',  type: 'int',                      default: 20,    required: false, description: 'Steps',    choices: null },
        { name: 'scale',  type: 'float',                    default: 7.5,   required: false, description: 'Scale',    choices: null },
    ],
};

// =============================================================================
// Helpers
// =============================================================================

/**
 * Minimal mock that satisfies RefractForm's client interface.
 * Override .call / .stream on the returned object per-test as needed.
 */
function makeMockClient(schemas = { greet: GREET_SCHEMA }) {
    const client = {
        _schemas: null,
        async loadSchemas() {
            this._schemas = schemas;
            return schemas;
        },
        getSchema(name) { return this._schemas?.[name] ?? null; },
        async call()    { return { result: 'mocked' }; },
        async *stream() {
            yield { event: 'token',    data: { chunk: 'hi'   } };
            yield { event: 'complete', data: { message: 'done' } };
        },
        _validateParams(params, schema) {
            const errors = {};
            for (const p of schema.parameters ?? []) {
                if (p.required && (params[p.name] === undefined || params[p.name] === null)) {
                    errors[p.name] = 'Required';
                }
            }
            return { valid: Object.keys(errors).length === 0, errors };
        },
    };
    return client;
}

/**
 * Creates a RefractForm with mock client and waits for it to be ready.
 */
async function makeForm(opts = {}, schemas = { greet: GREET_SCHEMA }) {
    const client = makeMockClient(schemas);
    const form   = new RefractForm({ ...opts, client });
    await form.ready;
    return { form, client };
}

/**
 * Returns a Promise that resolves with the detail of the next event.
 */
function captureEvent(target, name) {
    return new Promise(resolve =>
        target.addEventListener(name, e => resolve(e.detail), { once: true }),
    );
}

/**
 * Minimal fake "RefractForm-shaped" object for createParamInput auto-bind tests.
 * Has a .params getter and .set() so the overload detection triggers.
 */
function makeFakeForm(schema) {
    const store = {};
    for (const p of schema.parameters) {
        if (p.default !== null && p.default !== undefined) {
            store[p.name] = p.default;
        } else if (p.type === 'bool') {
            store[p.name] = false;
        } else if (p.choices?.length) {
            store[p.name] = p.choices[0];
        } else {
            store[p.name] = undefined;
        }
    }
    return {
        _store: store,
        get params() { return { ...this._store }; },
        set(name, value) { this._store[name] = value; },
    };
}

// Shorthand to build a param object with sensible defaults
const mkParam = (overrides = {}) => ({
    name: 'value',
    type: 'str',
    default: null,
    required: false,
    description: '',
    choices: null,
    ...overrides,
});

// =============================================================================
// RefractForm
// =============================================================================

describe('RefractForm', () => {

    // ── constructor & ready ───────────────────────────────────────────────────

    describe('constructor & ready', () => {
        it('is loading immediately after construction', () => {
            const client = makeMockClient();
            const form   = new RefractForm({ client });
            expect(form.isLoading).toBe(true);
        });

        it('ready resolves with the list of function schemas', async () => {
            const client = makeMockClient();
            const form   = new RefractForm({ client });
            const fns    = await form.ready;
            expect(fns).toHaveLength(1);
            expect(fns[0].name).toBe('greet');
        });

        it('isLoading is false after ready resolves', async () => {
            const { form } = await makeForm();
            expect(form.isLoading).toBe(false);
        });

        it('ready rejects when loadSchemas throws', async () => {
            const client = { async loadSchemas() { throw new Error('Network error'); } };
            const form   = new RefractForm({ client });
            await expect(form.ready).rejects.toThrow('Network error');
        });

        it('emits load event with functions array', async () => {
            const client   = makeMockClient();
            const form     = new RefractForm({ client });
            const { functions } = await captureEvent(form, 'load');
            expect(functions).toHaveLength(1);
            expect(functions[0].name).toBe('greet');
        });

        it('emits error event when loadSchemas fails', async () => {
            const netErr = new Error('Fail');
            const client = { async loadSchemas() { throw netErr; } };
            const form   = new RefractForm({ client });
            const detail = await captureEvent(form, 'error');
            expect(detail).toBe(netErr);
            await form.ready.catch(() => {}); // swallow rejection
        });
    });

    // ── filtering & auto-select ───────────────────────────────────────────────

    describe('filtering', () => {
        const MULTI = { greet: GREET_SCHEMA, stream_greet: STREAM_SCHEMA };

        it('filters by function name', async () => {
            const { form } = await makeForm({ function: 'greet' }, MULTI);
            expect(form.functions).toHaveLength(1);
            expect(form.functions[0].name).toBe('greet');
        });

        it('filters by tag', async () => {
            const schemas = { greet: GREET_SCHEMA, generate_image: IMAGE_SCHEMA };
            const { form } = await makeForm({ tag: 'image' }, schemas);
            expect(form.functions).toHaveLength(1);
            expect(form.functions[0].name).toBe('generate_image');
        });

        it('auto-selects when exactly one function matches', async () => {
            const { form } = await makeForm({ function: 'greet' }, MULTI);
            expect(form.selected?.name).toBe('greet');
        });

        it('does NOT auto-select when multiple functions match', async () => {
            const { form } = await makeForm({}, MULTI);
            expect(form.selected).toBeNull();
        });
    });

    // ── select ────────────────────────────────────────────────────────────────

    describe('select()', () => {
        it('sets selected to the named function', async () => {
            const { form } = await makeForm({}, { greet: GREET_SCHEMA, stream_greet: STREAM_SCHEMA });
            form.select('stream_greet');
            expect(form.selected?.name).toBe('stream_greet');
        });

        it('resets params to their defaults', async () => {
            const { form } = await makeForm();
            form.select('greet');
            expect(form.params.count).toBe(1);          // declared default
            expect(form.params.name).toBeUndefined();   // required, no default
        });

        it('clears any existing errors', async () => {
            const { form } = await makeForm();
            form.select('greet');
            form._errors = { name: 'Required' };
            form.select('greet');
            expect(form.errors.name).toBeUndefined();
        });

        it('emits select event with the schema', async () => {
            const { form } = await makeForm();
            const p = captureEvent(form, 'select');
            form.select('greet');
            const detail = await p;
            expect(detail.name).toBe('greet');
        });

        it('emits change event with updated state', async () => {
            const { form } = await makeForm();
            const p = captureEvent(form, 'change');
            form.select('greet');
            const { selected } = await p;
            expect(selected?.name).toBe('greet');
        });

        it('throws if function name is not in the loaded list', async () => {
            const { form } = await makeForm();
            expect(() => form.select('nonexistent')).toThrow();
        });
    });

    // ── set / setMany ─────────────────────────────────────────────────────────

    describe('set() / setMany()', () => {
        it('set() updates a single param', async () => {
            const { form } = await makeForm();
            form.select('greet');
            form.set('name', 'Alice');
            expect(form.params.name).toBe('Alice');
        });

        it('set() emits change with the new value', async () => {
            const { form } = await makeForm();
            form.select('greet');
            const p = captureEvent(form, 'change');
            form.set('name', 'Bob');
            const { params } = await p;
            expect(params.name).toBe('Bob');
        });

        it('set() does NOT validate', async () => {
            const { form } = await makeForm();
            form.select('greet');
            form.set('count', 'not-a-number'); // wrong type — no error
            expect(form.errors.count).toBeUndefined();
        });

        it('params getter returns a shallow copy (mutations do not affect internal state)', async () => {
            const { form } = await makeForm();
            form.select('greet');
            const snapshot = form.params;
            snapshot.name = 'mutated';
            expect(form.params.name).not.toBe('mutated');
        });

        it('setMany() with object merges into params', async () => {
            const { form } = await makeForm();
            form.select('greet');
            form.setMany({ name: 'Alice', count: 3 });
            expect(form.params.name).toBe('Alice');
            expect(form.params.count).toBe(3);
        });

        it('setMany() with callback receives a copy of current params', async () => {
            const { form } = await makeForm();
            form.select('greet');
            form.set('count', 5);
            let received;
            form.setMany(prev => { received = prev; return { ...prev, name: 'X' }; });
            expect(received.count).toBe(5);
            expect(form.params.name).toBe('X');
        });

        it('setMany() emits change exactly once', async () => {
            const { form } = await makeForm();
            form.select('greet');
            let count = 0;
            form.addEventListener('change', () => count++);
            form.setMany({ name: 'A', count: 2 });
            expect(count).toBe(1);
        });
    });

    // ── validate ──────────────────────────────────────────────────────────────

    describe('validate()', () => {
        it('returns { valid: true } when all required params are set', async () => {
            const { form } = await makeForm();
            form.select('greet');
            form.set('name', 'Alice');
            expect(form.validate().valid).toBe(true);
        });

        it('returns errors for missing required params', async () => {
            const { form } = await makeForm();
            form.select('greet');
            const { valid, errors } = form.validate();
            expect(valid).toBe(false);
            expect(errors.name).toBeTruthy();
        });

        it('populates form.errors', async () => {
            const { form } = await makeForm();
            form.select('greet');
            form.validate();
            expect(form.errors.name).toBeTruthy();
        });

        it('errors getter returns a shallow copy', async () => {
            const { form } = await makeForm();
            form.select('greet');
            form.validate();
            const snapshot = form.errors;
            snapshot.name = 'mutated';
            expect(form.errors.name).not.toBe('mutated');
        });

        it('emits change after validation', async () => {
            const { form } = await makeForm();
            form.select('greet');
            const p = captureEvent(form, 'change');
            form.validate();
            const { errors } = await p;
            expect(errors).toBeDefined();
        });

        it('throws if no function is selected', async () => {
            // Two schemas → no auto-select, so selected stays null
            const { form } = await makeForm({}, { greet: GREET_SCHEMA, stream_greet: STREAM_SCHEMA });
            expect(() => form.validate()).toThrow('No function selected');
        });
    });

    // ── reset ─────────────────────────────────────────────────────────────────

    describe('reset()', () => {
        it('restores params to their defaults', async () => {
            const { form } = await makeForm();
            form.select('greet');
            form.set('count', 99);
            form.reset();
            expect(form.params.count).toBe(1);
        });

        it('clears validation errors', async () => {
            const { form } = await makeForm();
            form.select('greet');
            form.validate();
            form.reset();
            expect(Object.keys(form.errors)).toHaveLength(0);
        });

        it('does nothing (no throw) when no function is selected', async () => {
            const { form } = await makeForm();
            expect(() => form.reset()).not.toThrow();
        });

        it('emits change after reset', async () => {
            const { form } = await makeForm();
            form.select('greet');
            const p = captureEvent(form, 'change');
            form.reset();
            await expect(p).resolves.toBeDefined();
        });
    });

    // ── submit — non-streaming ────────────────────────────────────────────────

    describe('submit() — non-streaming', () => {
        it('returns the result from client.call()', async () => {
            const client = makeMockClient();
            client.call  = async () => ({ answer: 42 });
            const form   = new RefractForm({ client });
            await form.ready;
            form.select('greet');
            form.set('name', 'Alice');
            expect(await form.submit()).toEqual({ answer: 42 });
        });

        it('emits submit-start → result → submit-end in order', async () => {
            const { form } = await makeForm();
            form.select('greet');
            form.set('name', 'Alice');
            const order = [];
            ['submit-start', 'result', 'submit-end'].forEach(n =>
                form.addEventListener(n, () => order.push(n)),
            );
            await form.submit();
            expect(order).toEqual(['submit-start', 'result', 'submit-end']);
        });

        it('isSubmitting is true during call and false after', async () => {
            const client     = makeMockClient();
            let seenDuring   = false;
            const formHolder = {};
            client.call = async () => {
                seenDuring = formHolder.form.isSubmitting;
                return {};
            };
            const form = new RefractForm({ client });
            formHolder.form = form;
            await form.ready;
            form.select('greet');
            form.set('name', 'A');
            await form.submit();
            expect(seenDuring).toBe(true);
            expect(form.isSubmitting).toBe(false);
        });

        it('throws and emits error when validation fails', async () => {
            const { form } = await makeForm();
            form.select('greet'); // name is undefined → required
            let errorDetail;
            form.addEventListener('error', e => (errorDetail = e.detail));
            await expect(form.submit()).rejects.toThrow('Validation failed');
            expect(errorDetail).toBeInstanceOf(Error);
        });

        it('emits submit-end even when client.call() throws', async () => {
            const client = makeMockClient();
            client.call  = async () => { throw new Error('Server error'); };
            const form   = new RefractForm({ client });
            await form.ready;
            form.select('greet');
            form.set('name', 'Alice');
            let endFired = false;
            form.addEventListener('submit-end', () => (endFired = true));
            await form.submit().catch(() => {});
            expect(endFired).toBe(true);
        });

        it('re-emits server error via error event', async () => {
            const client = makeMockClient();
            client.call  = async () => { throw new Error('500'); };
            const form   = new RefractForm({ client });
            await form.ready;
            form.select('greet');
            form.set('name', 'Alice');
            let errorFired = false;
            form.addEventListener('error', () => (errorFired = true));
            await form.submit().catch(() => {});
            expect(errorFired).toBe(true);
        });
    });

    // ── submit — streaming ────────────────────────────────────────────────────

    describe('submit() — streaming', () => {
        it('yields stream events for each SSE token', async () => {
            const client = makeMockClient({ stream_greet: STREAM_SCHEMA });
            client.stream = async function* () {
                yield { event: 'token',    data: { chunk: 'hello' } };
                yield { event: 'complete', data: { message: 'done' } };
            };
            const form = new RefractForm({ client });
            await form.ready;
            form.select('stream_greet');
            form.set('name', 'Alice');
            const tokens = [];
            form.addEventListener('stream', e => tokens.push(e.detail));
            await form.submit();
            expect(tokens).toHaveLength(2);
            expect(tokens[0]).toEqual({ event: 'token', data: { chunk: 'hello' } });
        });

        it('emits result with the last streamed data chunk', async () => {
            const client = makeMockClient({ stream_greet: STREAM_SCHEMA });
            client.stream = async function* () {
                yield { event: 'token',    data: { chunk: 'hi' }    };
                yield { event: 'complete', data: { message: 'done' } };
            };
            const form = new RefractForm({ client });
            await form.ready;
            form.select('stream_greet');
            form.set('name', 'Alice');
            const resultP = captureEvent(form, 'result');
            await form.submit();
            expect(await resultP).toEqual({ message: 'done' });
        });
    });

    // ── abort ─────────────────────────────────────────────────────────────────

    describe('abort()', () => {
        it('does not throw when called outside a submit', async () => {
            const { form } = await makeForm();
            expect(() => form.abort()).not.toThrow();
        });
    });

    // ── reload ────────────────────────────────────────────────────────────────

    describe('reload()', () => {
        it('creates a new ready Promise', async () => {
            const { form } = await makeForm();
            const first = form.ready;
            form.reload();
            expect(form.ready).not.toBe(first);
        });

        it('resets state and re-loads schemas', async () => {
            const { form } = await makeForm();
            form.select('greet');
            form.reload();
            await form.ready;
            // Single schema → auto-selected again
            expect(form.selected?.name).toBe('greet');
        });
    });

    // ── default params ────────────────────────────────────────────────────────

    describe('default params', () => {
        it('uses declared default value', async () => {
            const { form } = await makeForm();
            form.select('greet');
            expect(form.params.count).toBe(1);
        });

        it('bool param with null default → false', async () => {
            const schema = { ...IMAGE_SCHEMA, parameters: [
                { name: 'hd', type: 'bool', default: null, required: false, description: '', choices: null },
            ]};
            const client = makeMockClient({ generate_image: schema });
            const form   = new RefractForm({ client });
            await form.ready;
            form.select('generate_image');
            expect(form.params.hd).toBe(false);
        });

        it('choices param with null default → first choice', async () => {
            const schema = { ...IMAGE_SCHEMA, parameters: [
                { name: 'size', type: "Literal['sm','md']", default: null, required: false, description: '', choices: ['sm', 'md'] },
            ]};
            const client = makeMockClient({ generate_image: schema });
            const form   = new RefractForm({ client });
            await form.ready;
            form.select('generate_image');
            expect(form.params.size).toBe('sm');
        });

        it('required param with null default → undefined', async () => {
            const { form } = await makeForm();
            form.select('greet');
            expect(form.params.name).toBeUndefined();
        });
    });
});

// =============================================================================
// createParamInput
// =============================================================================

describe('createParamInput', () => {

    const manual = (value, onChange = () => {}) => ({ value, onChange });

    // ── element type mapping ──────────────────────────────────────────────────

    describe('element type mapping', () => {
        it('str → <input type="text">', () => {
            const el = createParamInput(mkParam({ name: 'title' }), manual(''));
            expect(el.tagName).toBe('INPUT');
            expect(el.type).toBe('text');
        });

        it('int → <input type="number" step="1">', () => {
            const el = createParamInput(mkParam({ name: 'count', type: 'int' }), manual(null));
            expect(el.tagName).toBe('INPUT');
            expect(el.type).toBe('number');
            expect(el.step).toBe('1');
        });

        it('float → <input type="number" step="0.1">', () => {
            const el = createParamInput(mkParam({ name: 'scale', type: 'float' }), manual(null));
            expect(el.type).toBe('number');
            expect(el.step).toBe('0.1');
        });

        it('bool → <input type="checkbox">', () => {
            const el = createParamInput(mkParam({ name: 'flag', type: 'bool' }), manual(null));
            expect(el.tagName).toBe('INPUT');
            expect(el.type).toBe('checkbox');
        });

        it('choices → <select> with correct number of options', () => {
            const el = createParamInput(mkParam({ name: 'size', choices: ['sm', 'md', 'lg'] }), manual(null));
            expect(el.tagName).toBe('SELECT');
            expect(el.options).toHaveLength(3);
        });

        it('"prompt" str → <textarea>', () => {
            const el = createParamInput(mkParam({ name: 'prompt', type: 'str' }), manual(''));
            expect(el.tagName).toBe('TEXTAREA');
        });

        it('"description" str → <textarea>', () => {
            const el = createParamInput(mkParam({ name: 'description', type: 'str' }), manual(''));
            expect(el.tagName).toBe('TEXTAREA');
        });

        it('"system_prompt" str → <textarea> (substring match)', () => {
            const el = createParamInput(mkParam({ name: 'system_prompt', type: 'str' }), manual(''));
            expect(el.tagName).toBe('TEXTAREA');
        });

        it('str? (Optional[str]) → <input type="text">', () => {
            const el = createParamInput(mkParam({ name: 'title', type: 'str?' }), manual(null));
            expect(el.tagName).toBe('INPUT');
            expect(el.type).toBe('text');
        });

        it('int? (Optional[int]) → <input type="number">', () => {
            const el = createParamInput(mkParam({ name: 'n', type: 'int?' }), manual(null));
            expect(el.type).toBe('number');
        });
    });

    // ── CSS classes ───────────────────────────────────────────────────────────

    describe('CSS classes', () => {
        it('text input has rf-input', () => {
            const el = createParamInput(mkParam(), manual(''));
            expect(el.classList.contains('rf-input')).toBe(true);
        });

        it('number input has rf-input', () => {
            const el = createParamInput(mkParam({ name: 'n', type: 'int' }), manual(null));
            expect(el.classList.contains('rf-input')).toBe(true);
        });

        it('checkbox has rf-input and rf-checkbox', () => {
            const el = createParamInput(mkParam({ name: 'flag', type: 'bool' }), manual(null));
            expect(el.classList.contains('rf-input')).toBe(true);
            expect(el.classList.contains('rf-checkbox')).toBe(true);
        });

        it('textarea has rf-input and rf-textarea', () => {
            const el = createParamInput(mkParam({ name: 'prompt', type: 'str' }), manual(''));
            expect(el.classList.contains('rf-input')).toBe(true);
            expect(el.classList.contains('rf-textarea')).toBe(true);
        });

        it('select has rf-select', () => {
            const el = createParamInput(mkParam({ name: 's', choices: ['a', 'b'] }), manual(null));
            expect(el.classList.contains('rf-select')).toBe(true);
        });
    });

    // ── data attributes ───────────────────────────────────────────────────────

    describe('data attributes', () => {
        it('sets data-rf-param to the parameter name', () => {
            const el = createParamInput(mkParam({ name: 'my_param' }), manual(null));
            expect(el.dataset.rfParam).toBe('my_param');
        });

        it('sets data-rf-type to the serialized Python type', () => {
            const el = createParamInput(mkParam({ name: 'n', type: 'int' }), manual(null));
            expect(el.dataset.rfType).toBe('int');
        });

        it('preserves str? in data-rf-type', () => {
            const el = createParamInput(mkParam({ name: 'x', type: 'str?' }), manual(null));
            expect(el.dataset.rfType).toBe('str?');
        });
    });

    // ── required & placeholder ────────────────────────────────────────────────

    describe('required & placeholder', () => {
        it('required param has required attribute', () => {
            const el = createParamInput(mkParam({ name: 'x', required: true }), manual(null));
            expect(el.required).toBe(true);
        });

        it('required param with no default → placeholder "Required"', () => {
            const el = createParamInput(mkParam({ name: 'x', required: true, default: null }), manual(null));
            expect(el.placeholder).toBe('Required');
        });

        it('param with default → placeholder "default: {value}"', () => {
            const el = createParamInput(mkParam({ name: 'n', type: 'int', default: 42 }), manual(null));
            expect(el.placeholder).toBe('default: 42');
        });

        it('optional param with no default → no placeholder', () => {
            const el = createParamInput(mkParam({ name: 'x', required: false, default: null }), manual(null));
            expect(el.placeholder).toBe('');
        });
    });

    // ── initial values ────────────────────────────────────────────────────────

    describe('initial values', () => {
        it('text input shows the initial string value', () => {
            const el = createParamInput(mkParam({ name: 'x' }), manual('hello'));
            expect(el.value).toBe('hello');
        });

        it('number input shows the initial numeric value', () => {
            const el = createParamInput(mkParam({ name: 'n', type: 'int' }), manual(5));
            expect(el.value).toBe('5');
        });

        it('checkbox is checked when initial value is true', () => {
            const el = createParamInput(mkParam({ name: 'flag', type: 'bool' }), manual(true));
            expect(el.checked).toBe(true);
        });

        it('checkbox is unchecked when initial value is false', () => {
            const el = createParamInput(mkParam({ name: 'flag', type: 'bool' }), manual(false));
            expect(el.checked).toBe(false);
        });

        it('select pre-selects the matching option', () => {
            const el = createParamInput(mkParam({ name: 's', choices: ['a', 'b', 'c'] }), manual('b'));
            expect(el.value).toBe('b');
        });

        it('select falls back to first choice if value is null', () => {
            const el = createParamInput(mkParam({ name: 's', choices: ['x', 'y'] }), manual(null));
            expect(el.value).toBe('x');
        });
    });

    // ── onChange callbacks ────────────────────────────────────────────────────

    describe('onChange callbacks', () => {
        it('text input calls onChange with string value', () => {
            let received;
            const el = createParamInput(mkParam({ name: 'x' }), manual('', v => (received = v)));
            el.value = 'world';
            el.dispatchEvent(new Event('input'));
            expect(received).toBe('world');
        });

        it('number input calls onChange with parsed integer', () => {
            let received;
            const el = createParamInput(mkParam({ name: 'n', type: 'int' }), manual(null, v => (received = v)));
            el.value = '7';
            el.dispatchEvent(new Event('input'));
            expect(received).toBe(7);
            expect(Number.isInteger(received)).toBe(true);
        });

        it('number input calls onChange with parsed float', () => {
            let received;
            const el = createParamInput(mkParam({ name: 'n', type: 'float' }), manual(null, v => (received = v)));
            el.value = '3.14';
            el.dispatchEvent(new Event('input'));
            expect(received).toBeCloseTo(3.14);
        });

        it('number input calls onChange with undefined on empty input', () => {
            let received = 'initial';
            const el = createParamInput(mkParam({ name: 'n', type: 'int' }), manual(5, v => (received = v)));
            el.value = '';
            el.dispatchEvent(new Event('input'));
            expect(received).toBeUndefined();
        });

        it('checkbox calls onChange with true when checked', () => {
            let received;
            const el = createParamInput(mkParam({ name: 'flag', type: 'bool' }), manual(false, v => (received = v)));
            el.checked = true;
            el.dispatchEvent(new Event('change'));
            expect(received).toBe(true);
        });

        it('select calls onChange with string value', () => {
            let received;
            const el = createParamInput(mkParam({ name: 's', choices: ['x', 'y'] }), manual('x', v => (received = v)));
            el.value = 'y';
            el.dispatchEvent(new Event('change'));
            expect(received).toBe('y');
        });

        it('select with numeric choices coerces onChange value to number', () => {
            let received;
            const el = createParamInput(mkParam({ name: 'n', choices: [1, 2, 3] }), manual(1, v => (received = v)));
            el.value = '3';
            el.dispatchEvent(new Event('change'));
            expect(received).toBe(3);
            expect(typeof received).toBe('number');
        });
    });

    // ── auto-bind overload (RefractForm) ──────────────────────────────────────

    describe('auto-bind overload', () => {
        it('reads initial value from form.params[name]', () => {
            const form  = makeFakeForm(GREET_SCHEMA);
            form._store.count = 5;
            const param = GREET_SCHEMA.parameters.find(p => p.name === 'count');
            const el    = createParamInput(param, form);
            expect(el.value).toBe('5');
        });

        it('calls form.set(name, value) on input change', () => {
            const form  = makeFakeForm(GREET_SCHEMA);
            const param = GREET_SCHEMA.parameters.find(p => p.name === 'count');
            const el    = createParamInput(param, form);
            el.value = '99';
            el.dispatchEvent(new Event('input'));
            expect(form._store.count).toBe(99); // int coercion
        });

        it('detects form by the presence of .set() method', () => {
            const notForm = { value: 'test', onChange: () => {} }; // has onChange, not set
            const param   = mkParam({ name: 'x' });
            expect(() => createParamInput(param, notForm)).not.toThrow();
        });

        it('works with bool param — calls form.set with boolean', () => {
            const form  = makeFakeForm(IMAGE_SCHEMA);
            const param = IMAGE_SCHEMA.parameters.find(p => p.name === 'hd');
            const el    = createParamInput(param, form);
            el.checked = true;
            el.dispatchEvent(new Event('change'));
            expect(form._store.hd).toBe(true);
        });

        it('works with select param — calls form.set with string', () => {
            const form  = makeFakeForm(IMAGE_SCHEMA);
            const param = IMAGE_SCHEMA.parameters.find(p => p.name === 'size');
            const el    = createParamInput(param, form);
            el.value = '1024';
            el.dispatchEvent(new Event('change'));
            expect(form._store.size).toBe('1024');
        });
    });
});
