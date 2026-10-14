const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createRequire } = require("node:module");

const root = path.resolve(__dirname, "..");
const component = process.env.LOCATION_SELECTOR_SOURCE || path.join(root, "homebox-ui/overlay/components/Location/Selector.vue");
const requireVue = createRequire(path.join(root, "label-ui/package.json"));
const vue = requireVue("vue");
const { parse, compileScript } = require(path.join(root, "label-ui/node_modules/.pnpm/@vue+compiler-sfc@3.5.39/node_modules/@vue/compiler-sfc"));
const esbuild = require(path.join(root, "work/homebox-ui-build/node_modules/.pnpm/esbuild@0.27.7/node_modules/esbuild"));

async function loadComponent() {
  const { descriptor, errors } = parse(fs.readFileSync(component, "utf8"), { filename: component });
  assert.deepEqual(errors, []);
  const script = compileScript(descriptor, { id: "location-selector-test", inlineTemplate: true });
  const outfile = path.join(os.tmpdir(), `location-selector-${process.pid}.cjs`);
  const ui = `
    import { h, inject, provide, cloneVNode } from "vue";
    const wrap = name => ({ setup(_props, { attrs, slots }) { return () => h(name, attrs, slots.default?.()); } });
    export const Button = { setup(_props, { attrs, slots }) { return () => h("button", attrs, slots.default?.()); } };
    export const Label = wrap("label");
    export const Command = wrap("div"), CommandEmpty = wrap("div"), CommandGroup = wrap("div"), CommandList = wrap("div");
    export const CommandInput = { props: ["modelValue"], emits: ["update:modelValue"], setup(props, { emit, attrs }) { return () => h("input", { ...attrs, value: props.modelValue, onInput: e => emit("update:modelValue", e.target.value) }); } };
    export const CommandItem = { emits: ["select"], setup(_props, { attrs, slots, emit }) { return () => h("div", { ...attrs, onClick: () => emit("select") }, slots.default?.()); } };
    export const Popover = { props: ["open"], emits: ["update:open"], setup(_props, { slots, emit }) { provide("setPopoverOpen", value => emit("update:open", value)); return () => h("div", slots.default?.()); } };
    export const PopoverContent = wrap("div");
    export const PopoverTrigger = { props: ["asChild"], setup(_props, { slots }) { const setOpen = inject("setPopoverOpen"); return () => { const children = slots.default?.() || []; return children.map(child => cloneVNode(child, { onClick: () => setOpen(true) })); }; } };
    export const Check = wrap("i"), ChevronsDown = wrap("i"), ChevronsUpDown = wrap("i"), ChevronRight = wrap("i"), X = wrap("i");
  `;
  const result = await esbuild.build({
    stdin: { contents: script.content, sourcefile: "LocationSelector.ts", loader: "ts", resolveDir: path.dirname(component) },
    bundle: true, write: false, format: "cjs", platform: "node",
    plugins: [{
      name: "location-selector-test-stubs",
      setup(build) {
        build.onResolve({ filter: /^vue$/ }, () => ({ path: requireVue.resolve("vue"), external: true }));
        build.onResolve({ filter: /^lucide-vue-next$/ }, () => ({ path: "ui", namespace: "stub" }));
        build.onResolve({ filter: /^fuzzysort$/ }, () => ({ path: "fuzzysort", namespace: "stub" }));
        build.onResolve({ filter: /^~\/components\/ui\// }, args => ({ path: args.path, namespace: "stub" }));
        build.onResolve({ filter: /^~\/lib\/utils$/ }, () => ({ path: "utils", namespace: "stub" }));
        build.onLoad({ filter: /.*/, namespace: "stub" }, args => ({
          contents: args.path === "fuzzysort"
            ? 'export default { go(search, rows, options) { const q = search.toLowerCase(); return rows.filter(row => row[options.key].toLowerCase().includes(q)).map(obj => ({ obj })); } };'
            : args.path === "utils" ? 'export const cn = (...classes) => classes.filter(Boolean).join(" ");' : ui,
          loader: "js",
        }));
      },
    }],
  });
  fs.writeFileSync(outfile, result.outputFiles[0].contents);
  try { return require(outfile).default; } finally { fs.rmSync(outfile, { force: true }); }
}

function makeLocation(id, name, parent, extra = {}) { return { id, name, parent: parent ? { id: parent } : undefined, ...extra }; }
const data = [
  makeLocation("shop", "Shop"),
  makeLocation("shelf", "Shelf", "shop"),
  makeLocation("bin", "Bin", "shelf"),
  makeLocation("other", "Other"),
  makeLocation("archived", "Old room", undefined, { archived: true }),
  makeLocation("excluded", "Current room"),
];

function fixture(Component, modelValue = null) {
  const ops = {
    createElement: type => ({ type, props: {}, children: [], parent: null, listeners: {}, getRootNode() { return this; }, addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }, removeEventListener(name, fn) { this.listeners[name] = (this.listeners[name] || []).filter(row => row !== fn); } }),
    createText: text => ({ type: "#text", text, parent: null }),
    createComment: text => ({ type: "#comment", text, parent: null }),
    setText(node, text) { node.text = text; },
    setElementText(node, text) { node.text = text; node.children = []; },
    patchProp(node, key, _old, value) { node.props[key] = value; if (key === "value") node.value = value; },
    insert(node, parent, anchor) { node.parent = parent; const at = anchor ? parent.children.indexOf(anchor) : -1; if (at < 0) parent.children.push(node); else parent.children.splice(at, 0, node); },
    remove(node) { if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = null; },
    parentNode: node => node.parent,
    nextSibling(node) { const list = node.parent?.children || []; return list[list.indexOf(node) + 1] || null; },
  };
  global.ref = vue.ref; global.computed = vue.computed; global.watch = vue.watch; global.onBeforeUnmount = vue.onBeforeUnmount;
  global.useId = () => "location-selector";
  global.useCollections = () => ({ selectedId: vue.ref("collection") });
  global.useAuthContext = () => ({ user: { id: "user" } });
  global.useUserApi = () => ({ items: { getAll: async ({ isLocation }) => ({ data: { items: isLocation ? data : [], total: isLocation ? data.length : 0 } }) } });
  global.useVModel = (props, key, emit) => vue.computed({ get: () => props[key], set: value => emit(`update:${key}`, value) });
  const renderer = vue.createRenderer(ops), rootNode = { type: "root", children: [] }, selected = [];
  const app = renderer.createApp(Component, {
    modelValue,
    excludeIds: ["excluded"],
    "onUpdate:modelValue": value => { selected.push(value); app._instance.props.modelValue = value; },
  });
  app.config.globalProperties.$t = key => key;
  app.mount(rootNode);
  const all = (node, pred) => (pred(node) ? [node] : []).concat((node.children || []).flatMap(child => all(child, pred)));
  const text = node => node.text ?? (node.children || []).map(text).join("");
  const button = label => all(rootNode, n => n.type === "button" && text(n).trim() === label)[0];
  const namedButton = label => all(rootNode, n => n.type === "button" && n.props["aria-label"] === label)[0];
  const trigger = () => all(rootNode, n => n.type === "button" && n.props["aria-haspopup"] === "dialog")[0];
  const searchInput = () => all(rootNode, n => n.type === "input" && n.props.type === "search")[0];
  return { rootNode, selected, button, namedButton, trigger, searchInput, all, text, render: () => app.unmount() };
}
const tick = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); await vue.nextTick(); };

(async () => {
  const Component = await loadComponent();

  // Browse starts at roots; expanding is separate from selecting and stays open.
  {
    const ui = fixture(Component);
    ui.trigger().props.onClick({});
    await tick();
    assert.ok(ui.button("Shop"));
    assert.ok(ui.button("Other"));
    assert.equal(ui.button("Shelf"), undefined);
    ui.namedButton("Expand Shop").props.onClick({ stopPropagation() {} });
    await tick();
    assert.ok(ui.button("Shelf"));
    assert.equal(ui.button("Bin"), undefined);
    assert.equal(ui.selected.length, 0, "expansion must not select a location");
    assert.equal(ui.trigger().props["aria-expanded"], true, "expansion must leave the dropdown open");
    ui.namedButton("Expand Shelf").props.onClick({ stopPropagation() {} });
    await tick();
    assert.ok(ui.button("Bin"), "grandchildren appear after expanding their parent");
    assert.equal(ui.button("Old room"), undefined, "archived locations stay hidden");
    assert.equal(ui.button("Current room"), undefined, "excluded locations stay hidden");
    ui.button("Bin").props.onClick({ stopPropagation() {} });
    await tick();
    assert.equal(ui.selected.at(-1).id, "bin");
    assert.equal(ui.trigger().props["aria-expanded"], false, "selecting closes the dropdown");
    ui.render();
  }

  // An existing nested selection opens with its ancestors visible, and no-parent remains selectable.
  {
    const ui = fixture(Component, data[2]);
    ui.trigger().props.onClick({});
    await tick();
    assert.ok(ui.button("Shelf"));
    assert.ok(ui.button("Bin"));
    ui.button("Top level / no parent").props.onClick({ stopPropagation() {} });
    assert.equal(ui.selected.at(-1), null);
  }

  // Search still finds nested entries by ancestry and provides native selection and Escape.
  {
    const ui = fixture(Component);
    ui.trigger().props.onClick({});
    await tick();
    const input = ui.searchInput();
    input.props.onInput({ target: { value: "shelf" } });
    await tick();
    const match = ui.all(ui.rootNode, n => n.type === "button" && ui.text(n).includes("Shop / Shelf"))[0];
    assert.ok(match, "search result keeps its full ancestry context");
    input.props.onKeydown({ key: "Escape", stopPropagation() {}, preventDefault() {} });
    await tick();
    assert.equal(ui.trigger().props["aria-expanded"], false, "Escape closes the search popover");
    ui.trigger().props.onClick({});
    await tick();
    match.props.onClick({});
    await tick();
    assert.equal(ui.selected.at(-1).id, "shelf");
    assert.equal(ui.trigger().props["aria-expanded"], false);
    ui.trigger().props.onClick({});
    await tick();
    assert.equal(ui.searchInput().props.value, "", "reopening resets the search query");
    assert.ok(ui.button("Shelf"), "reopening reveals the selected location ancestry");
    ui.render();
  }

  process.stdout.write("Location Selector component tree checks: 3 passed\n");
})().catch(error => { console.error(error); process.exitCode = 1; });
