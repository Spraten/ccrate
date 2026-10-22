(() => {
  const themes = new Set(['homebox','light','dark','cupcake','bumblebee','emerald','corporate','synthwave','retro','cyberpunk','valentine','halloween','garden','forest','aqua','lofi','pastel','fantasy','wireframe','black','luxury','dracula','cmyk','autumn','business','acid','lemonade','night','coffee','winter']);
  fetch('/api/theme', { cache: 'no-store', credentials: 'same-origin' })
    .then(response => response.ok ? response.json() : null)
    .then(data => {
      const theme = data && themes.has(data.theme) ? data.theme : 'homebox';
      const root = document.documentElement;
      [...root.classList].filter(name => name.startsWith('theme-')).forEach(name => root.classList.remove(name));
      root.classList.add(`theme-${theme}`);
      root.dataset.theme = theme;
    }).catch(() => {});
})();
