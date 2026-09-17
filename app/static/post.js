(() => {
  const title = document.querySelector('[data-fit-title]');
  if (!title) return;

  const fitTitle = () => {
    const rootSize = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
    const maxSize = 3.6 * rootSize;
    const minSize = 1.15 * rootSize;

    title.style.fontSize = `${maxSize}px`;

    if (title.scrollWidth <= title.clientWidth) return;

    let low = minSize;
    let high = maxSize;
    for (let i = 0; i < 14; i++) {
      const mid = (low + high) / 2;
      title.style.fontSize = `${mid}px`;
      if (title.scrollWidth <= title.clientWidth) low = mid;
      else high = mid;
    }
    title.style.fontSize = `${low}px`;
  };

  fitTitle();
  new ResizeObserver(fitTitle).observe(title.parentElement);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitTitle);
})();
