(() => {
  const search = document.querySelector('#story-search');
  const links = Array.from(document.querySelectorAll('[data-nav-section]'));
  const stories = Array.from(document.querySelectorAll('[data-story]'));
  const empty = document.querySelector('#empty-state');
  const clear = document.querySelector('#clear-filter');
  if (!search || !links.length || !empty || !clear) return;

  const sections = new Set(links.map((link) => link.dataset.navSection));
  const requested = new URLSearchParams(window.location.search).get('section');
  const section = sections.has(requested) ? requested : 'all';
  const normalize = (value) => value.normalize('NFKC').trim().toLocaleLowerCase();

  links.forEach((link) => {
    if (link.dataset.navSection === section) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  clear.hidden = section === 'all';

  function render() {
    const query = normalize(search.value);
    let visible = 0;
    stories.forEach((story) => {
      const matchesSection = section === 'all' || story.dataset.section === section;
      const matchesText = !query || normalize(story.textContent).includes(query);
      story.hidden = !(matchesSection && matchesText);
      if (!story.hidden) visible += 1;
    });
    empty.hidden = visible > 0;
  }

  search.addEventListener('input', render);
  render();
})();

(() => {
  const article = document.querySelector('.article');
  const body = article?.querySelector('.article-body');
  const toc = article?.querySelector('.article-toc');
  const details = toc?.querySelector('.article-toc-disclosure');
  const nav = toc?.querySelector('.article-toc-nav');
  if (!body || !details || !nav) return;

  const headings = Array.from(body.querySelectorAll('h2, h3'));
  if (!headings.length) return;

  const reservedIds = new Set(Array.from(document.querySelectorAll('[id]'), (element) => element.id));
  const usedIds = new Set();
  const list = document.createElement('ol');
  const entries = [];
  let parentItem;

  headings.forEach((heading, index) => {
    if (!heading.id || usedIds.has(heading.id) || document.getElementById(heading.id) !== heading) {
      let id = `article-section-${index + 1}`;
      while (reservedIds.has(id)) id += '-section';
      heading.id = id;
      reservedIds.add(id);
    }
    usedIds.add(heading.id);

    const item = document.createElement('li');
    const link = document.createElement('a');
    link.href = `#${encodeURIComponent(heading.id)}`;
    link.textContent = heading.textContent.trim();
    item.append(link);
    if (heading.tagName === 'H3' && parentItem) {
      let sublist = parentItem.querySelector('ol');
      if (!sublist) {
        sublist = document.createElement('ol');
        parentItem.append(sublist);
      }
      sublist.append(item);
    } else {
      list.append(item);
      parentItem = heading.tagName === 'H2' ? item : undefined;
    }
    entries.push(link);
  });

  nav.append(list);
  toc.hidden = false;
  article.classList.add('has-toc');

  const desktop = window.matchMedia('(min-width: 900px)');
  details.open = desktop.matches;
  desktop.addEventListener('change', () => { details.open = desktop.matches; });

  let activeIndex = -1;
  function revealActive() {
    if (!details.open || activeIndex < 0) return;
    const bounds = nav.getBoundingClientRect();
    const linkBounds = entries[activeIndex].getBoundingClientRect();
    if (linkBounds.top < bounds.top) nav.scrollTop += linkBounds.top - bounds.top;
    else if (linkBounds.bottom > bounds.bottom) nav.scrollTop += linkBounds.bottom - bounds.bottom;
  }

  function updateCurrent() {
    const threshold = Math.min(140, window.innerHeight * 0.25);
    let current = 0;
    headings.forEach((heading, index) => {
      if (heading.getBoundingClientRect().top <= threshold) current = index;
    });
    const atPageEnd = window.scrollY > 0 && window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2;
    if (atPageEnd && headings[headings.length - 1].getBoundingClientRect().top < window.innerHeight) current = headings.length - 1;
    if (current === activeIndex) return;
    if (activeIndex >= 0) entries[activeIndex].removeAttribute('aria-current');
    activeIndex = current;
    entries[activeIndex].setAttribute('aria-current', 'location');
    revealActive();
  }

  let scheduled = false;
  function scheduleUpdate() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(() => {
      scheduled = false;
      updateCurrent();
    });
  }

  nav.addEventListener('click', (event) => {
    if (!desktop.matches && event.target.closest('a')) details.open = false;
  });
  details.addEventListener('toggle', revealActive);
  window.addEventListener('scroll', scheduleUpdate, { passive: true });
  window.addEventListener('resize', scheduleUpdate);
  updateCurrent();
})();
