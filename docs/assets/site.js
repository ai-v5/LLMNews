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
