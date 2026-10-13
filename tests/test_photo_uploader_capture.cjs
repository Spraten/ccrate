const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createRequire } = require("node:module");

const root = path.resolve(__dirname, "..");
const component = path.join(root, "homebox-ui/overlay/components/Form/PhotoUploader.vue");
const labelRequire = createRequire(path.join(root, "label-ui/package.json"));
const { parse, compileScript } = require(path.join(root, "label-ui/node_modules/.pnpm/@vue+compiler-sfc@3.5.39/node_modules/@vue/compiler-sfc"));
const vue = labelRequire("vue");
const esbuild = require(path.join(root, "work/homebox-ui-build/node_modules/.pnpm/esbuild@0.27.7/node_modules/esbuild"));

async function loadComponent() {
  const { descriptor, errors } = parse(fs.readFileSync(component, "utf8"), { filename: component });
  assert.deepEqual(errors, []);
  const script = compileScript(descriptor, { id: "photo-uploader-test", inlineTemplate: true });
  const outfile = path.join(os.tmpdir(), `photo-uploader-${process.pid}.cjs`);
  const ui = `
    import { h } from "vue";
    export const Button = { setup(_props, { attrs, slots }) { return () => h("button", attrs, slots.default?.()); } };
    export const Label = { setup(_props, { attrs, slots }) { return () => h("label", attrs, slots.default?.()); } };
  `;
  const result = await esbuild.build({
    stdin: { contents: script.content, sourcefile: "PhotoUploader.ts", loader: "ts", resolveDir: path.dirname(component) },
    bundle: true,
    write: false,
    format: "cjs",
    platform: "node",
    plugins: [{
      name: "component-test-stubs",
      setup(build) {
        build.onResolve({ filter: /^vue$/ }, () => ({ path: require.resolve("vue", { paths: [path.join(root, "label-ui")] }), external: true }));
        build.onResolve({ filter: /^vue-i18n$/ }, () => ({ path: "vue-i18n", namespace: "stub" }));
        build.onResolve({ filter: /^~\/components\/ui\/(button|label)$/ }, args => ({ path: args.path, namespace: "stub" }));
        build.onResolve({ filter: /^\.\/photo-uploader$/ }, () => ({ path: path.join(root, "upstream/homebox/frontend/components/Form/photo-uploader.ts") }));
        build.onLoad({ filter: /.*/, namespace: "stub" }, args => ({
          contents: args.path === "vue-i18n" ? 'export const useI18n = () => ({ t: key => key });' : ui,
          loader: "ts",
        }));
      },
    }],
  });
  fs.writeFileSync(outfile, result.outputFiles[0].contents);
  try { return require(outfile).default; }
  finally { fs.rmSync(outfile, { force: true }); }
}

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

function fixture(Component, media) {
  Object.defineProperty(global, "navigator", { configurable: true, value: { mediaDevices: { getUserMedia: media.getUserMedia } } });
  global.URL.createObjectURL = () => "blob:captured";
  global.URL.revokeObjectURL = () => {};
  global.FileReader = class {
    readAsDataURL(file) { this.result = `data:${file.type};base64,AA==`; queueMicrotask(() => this.onload({ target: this })); }
  };
  const ops = {
    createElement(type) {
      const node = { type, props: {}, children: [], parent: null, videoWidth: 640, videoHeight: 480 };
      if (type === "canvas") {
        node.getContext = () => ({ drawImage() {} });
        node.toBlob = callback => media.toBlob(callback);
      }
      return node;
    },
    createText: text => ({ type: "#text", text, parent: null }),
    createComment: text => ({ type: "#comment", text, parent: null }),
    setText(node, text) { node.text = text; },
    setElementText(node, text) { node.text = text; node.children = []; },
    patchProp(node, key, _old, value) { node.props[key] = value; },
    insert(node, parent, anchor) {
      node.parent = parent;
      if (!parent.children) parent.children = [];
      const at = anchor ? parent.children.indexOf(anchor) : -1;
      if (at < 0) parent.children.push(node); else parent.children.splice(at, 0, node);
    },
    remove(node) { if (node.parent?.children) node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = null; },
    parentNode: node => node.parent,
    nextSibling(node) { const list = node.parent?.children || []; return list[list.indexOf(node) + 1] || null; },
  };
  const renderer = vue.createRenderer(ops);
  const rootNode = { type: "root", children: [] };
  const selected = [];
  const vnode = vue.h(Component, { existingCount: 1, label: "Photos", buttonLabel: "Upload photos", onSelected: photos => selected.push(photos) });
  renderer.render(vnode, rootNode);
  const all = (node, pred) => (pred(node) ? [node] : []).concat((node.children || []).flatMap(child => all(child, pred)));
  const text = node => node.text ?? (node.children || []).map(text).join("");
  const button = name => {
    const node = all(rootNode, n => n.type === "button" && text(n) === name)[0];
    assert.ok(node, `button ${name} exists`);
    return node;
  };
  const click = name => button(name).props.onClick?.({});
  return { rootNode, selected, button, click, text, render: () => renderer.render(null, rootNode), all };
}

function track() { return { stopped: false, stop() { this.stopped = true; } }; }
function stream(t = track()) { return { track: t, getTracks: () => [t] }; }
const tick = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };

(async () => {
  const Component = await loadComponent();

  // A pending camera permission result after Cancel must stop its stream.
  {
    const permission = deferred(), cameraTrack = track();
    const ui = fixture(Component, { getUserMedia: () => permission.promise, toBlob: cb => cb(new Blob(["jpeg"], { type: "image/jpeg" })) });
    ui.click("Take photo"); await vue.nextTick(); ui.click("Cancel");
    permission.resolve(stream(cameraTrack)); await tick();
    assert.equal(cameraTrack.stopped, true);
    assert.equal(ui.selected.length, 0);
  }

  // A delayed canvas callback after Cancel must not restore a preview.
  {
    const cameraTrack = track(), blob = deferred();
    const ui = fixture(Component, { getUserMedia: async () => stream(cameraTrack), toBlob: cb => { blob.resolve(cb); } });
    ui.click("Take photo"); await tick(); await vue.nextTick();
    ui.click("Capture"); ui.click("Cancel");
    (await blob.promise)(new Blob(["jpeg"], { type: "image/jpeg" })); await tick();
    assert.equal(cameraTrack.stopped, true);
    assert.equal(ui.all(ui.rootNode, n => n.type === "img" && n.props.alt === "Captured photo preview").length, 0);
  }

  // Only Use photo emits, and existingCount keeps a later photo non-primary.
  {
    const cameraTrack = track();
    const ui = fixture(Component, { getUserMedia: async () => stream(cameraTrack), toBlob: cb => cb(new Blob(["jpeg"], { type: "image/jpeg" })) });
    ui.click("Take photo"); await tick(); await vue.nextTick();
    ui.click("Capture"); await tick(); await vue.nextTick();
    assert.equal(ui.selected.length, 0);
    ui.click("Use photo"); await tick();
    assert.equal(ui.selected.length, 1);
    assert.equal(ui.selected[0].length, 1);
    assert.equal(ui.selected[0][0].file.type, "image/jpeg");
    assert.equal(ui.selected[0][0].primary, false);
    assert.equal(cameraTrack.stopped, true);
  }

  // Leaving the owning modal/component releases an active stream.
  {
    const cameraTrack = track();
    const ui = fixture(Component, { getUserMedia: async () => stream(cameraTrack), toBlob: cb => cb(new Blob()) });
    ui.click("Take photo"); await tick();
    ui.render();
    assert.equal(cameraTrack.stopped, true);
  }

  process.stdout.write("PhotoUploader fake-camera component checks: 4 passed\n");
})().catch(error => { console.error(error); process.exitCode = 1; });
