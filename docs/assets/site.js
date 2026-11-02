(() => {
  const search = document.querySelector('#story-search');
  const buttons = Array.from(document.querySelectorAll('.filter'));
  const stories = Array.from(document.querySelectorAll('[data-story]'));
  const empty = document.querySelector('#empty-state');
  if (!search || !buttons.length || !empty) return;

  const sections = new Set(buttons.map((button) => button.dataset.section));
  const requested = new URLSearchParams(window.location.search).get('section');
  let section = sections.has(requested) ? requested : 'all';
  const normalize = (value) => value.normalize('NFKC').trim().toLocaleLowerCase();

  function render() {
    const query = normalize(search.value);
    let visible = 0;
    buttons.forEach((button) => {
      const active = button.dataset.section === section;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    stories.forEach((story) => {
      const matchesSection = section === 'all' || story.dataset.section === section;
      const matchesText = !query || normalize(story.textContent).includes(query);
      story.hidden = !(matchesSection && matchesText);
      if (!story.hidden) visible += 1;
    });
    empty.hidden = visible > 0;
  }

  buttons.forEach((button) => button.addEventListener('click', () => {
    section = button.dataset.section;
    render();
  }));
  search.addEventListener('input', render);
  render();
})();
