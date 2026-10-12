'use strict';
// Add shared workshop workflows without changing Homebox's upstream build.
(() => {
  if (window.self !== window.top || document.querySelector('#homebox-equipment-tools')) return;
  const style = document.createElement('style');
  style.textContent = `
    #homebox-equipment-tools{position:fixed;bottom:18px;right:18px;z-index:45;display:flex;gap:8px;padding:8px;border:1px solid #b7d5cc;border-radius:12px;background:#fff;box-shadow:0 3px 18px #182a3826;font:14px system-ui}
    #homebox-equipment-tools button{border:0;border-radius:7px;padding:10px 13px;background:#206756;color:#fff;cursor:pointer}
    #homebox-equipment-dialog{width:96vw;max-width:1500px;height:94dvh;padding:0;border:1px solid #b7d5cc;border-radius:12px;background:#f7fafb;color:#203448}
    #homebox-equipment-dialog::backdrop{background:#182a3870}
    #homebox-equipment-dialog header{display:flex;align-items:center;justify-content:space-between;padding:10px 16px;font:16px system-ui;border-bottom:1px solid #cedae2}
    #homebox-equipment-dialog button{padding:8px 16px;border:1px solid #cedae2;border-radius:7px;cursor:pointer;background:white;color:#203448}
    #homebox-equipment-dialog iframe{display:block;width:100%;height:calc(100% - 57px);border:0}
    #homebox-equipment-tools button:focus-visible,#homebox-equipment-dialog button:focus-visible{outline:3px solid #b66b08;outline-offset:3px}
    @media(max-width:600px){#homebox-equipment-tools{bottom:8px;right:8px;left:8px;justify-content:center}#homebox-equipment-tools button{padding:9px;font-size:12px}}
  `;
  document.head.append(style);
  const bar = document.createElement('nav');
  bar.id = 'homebox-equipment-tools';
  bar.setAttribute('aria-label', 'Shared equipment tools');
  const dialog = document.createElement('dialog');
  dialog.id = 'homebox-equipment-dialog';
  dialog.setAttribute('aria-labelledby', 'homebox-equipment-title');
  const header = document.createElement('header'), title = document.createElement('strong');
  title.id = 'homebox-equipment-title';
  const close = document.createElement('button');
  close.textContent = 'Back to Homebox';
  const frame = document.createElement('iframe');
  frame.title = 'Equipment management';
  header.append(title, close); dialog.append(header, frame);
  // Keep the page and its pending request/print state when closing the panel.
  close.onclick = () => dialog.close();
  let lastSource = '';
  function open(name, source) {
    if (lastSource !== source && lastSource) {
      if (!window.confirm('Save any unfinished work in the equipment panel before switching tools. Continue?')) return;
    }
    title.textContent = name;
    if (lastSource !== source) { frame.src = source; lastSource = source; }
    if (!dialog.open) dialog.showModal();
    if (source.startsWith('/workshop')) {
      try { frame.contentWindow.dispatchEvent(new Event('focus')); } catch {}
    }
  }
  const terminal = new URL(location.href);
  terminal.port = '17749'; terminal.pathname = '/'; terminal.search = '?mode=editor'; terminal.hash = '';
  for (const [name, source] of [['People & badges', '/workshop/#people'], ['Workshop tools', '/workshop/'], ['Equipment Terminal', terminal.href]]) {
    const button = document.createElement('button');
    button.type = 'button'; button.textContent = name;
    button.onclick = () => open(name, source);
    bar.append(button);
  }
  document.body.append(bar, dialog);
})();
