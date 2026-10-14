(function(root) {
  function bindScannerInput(input, onScan) {
    input.addEventListener('keydown', event => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      const code = input.value.trim();
      input.value = '';
      if (code) onScan(code);
    });
  }

  function mountScannerCapture(overlay, onScan) {
    const panel = document.createElement('section');
    panel.className = 'notice';
    panel.style = 'max-width:680px;margin-bottom:12px';
    const title = document.createElement('h2');
    title.textContent = 'NETUM 2D-C750-Yellow · Bluetooth keyboard mode';
    const help = document.createElement('p');
    help.textContent = 'Power on the scanner. In your computer’s Bluetooth settings, pair “NETUM 2D-C750-Yellow” and choose HID/keyboard mode if prompted. If it does not appear, scan the Bluetooth HID setup barcode in the NETUM guide, then pair again. Click Focus scanner input, then scan. This page cannot read pairing or connection state.';
    const status = document.createElement('p');
    status.setAttribute('role', 'status');
    status.textContent = 'Scanner input unfocused. Click Focus scanner input to receive scans. Last scan: none';
    const input = document.createElement('input');
    input.type = 'text';
    input.autocomplete = 'off';
    input.autocapitalize = 'off';
    input.spellcheck = false;
    input.inputMode = 'none';
    input.setAttribute('aria-label', 'Focused barcode scanner input');
    input.placeholder = 'Focus here, then scan';
    let lastScan = 'none';
    let isFocused = false;
    input.addEventListener('focus', () => {
      isFocused = true;
      status.textContent = 'Ready to receive. Last scan: ' + lastScan;
    });
    input.addEventListener('blur', () => {
      isFocused = false;
      status.textContent = 'Scanner input unfocused. Click Focus scanner input to receive scans. Last scan: ' + lastScan;
    });
    const focusButton = document.createElement('button');
    focusButton.type = 'button';
    focusButton.textContent = 'Focus scanner input';
    focusButton.onclick = () => input.focus();
    bindScannerInput(input, async code => {
      lastScan = code;
      status.textContent = 'Checking scan… Last scan: ' + lastScan;
      try {
        const result = await onScan(code);
        if (!panel.isConnected) return;
        const unfocused = isFocused ? '' : ' · Scanner input unfocused. Click Focus scanner input to receive scans.';
        status.textContent = result === true
          ? (isFocused ? 'Ready to receive. Last scan: ' : 'Scanner input unfocused. Click Focus scanner input to receive scans. Last scan: ') + lastScan
          : String(result || 'Code not recognized') + unfocused + ' · Last scan: ' + lastScan;
      } catch (error) {
        if (panel.isConnected) {
          status.textContent = error.message + (isFocused ? '' : ' · Scanner input unfocused. Click Focus scanner input to receive scans.') + ' · Last scan: ' + lastScan;
        }
      }
    });
    panel.append(title, help, input, focusButton, status);
    overlay.append(panel);
    return input;
  }

  root.bindScannerInput = bindScannerInput;
  root.mountScannerCapture = mountScannerCapture;
  if (typeof module !== 'undefined') module.exports = { bindScannerInput, mountScannerCapture };
})(typeof window === 'undefined' ? globalThis : window);
