(() => {
  const key = 'llmnews-analytics-consent';
  const measurementId = 'G-KSJRJQMD1Q';
  const banner = document.getElementById('analytics-consent');
  let choice = null;
  try { choice = localStorage.getItem(key); } catch (_) { /* Ask again next visit. */ }

  function loadAnalytics() {
    if (document.getElementById('llmnews-ga4')) return;
    window.dataLayer = window.dataLayer || [];
    function gtag() { window.dataLayer.push(arguments); }
    gtag('js', new Date());
    gtag('config', measurementId);
    const script = document.createElement('script');
    script.id = 'llmnews-ga4';
    script.async = true;
    script.src = 'https://www.googletagmanager.com/gtag/js?id=' + measurementId;
    document.head.appendChild(script);
  }

  function save(value) {
    try { localStorage.setItem(key, value); } catch (_) { /* Choice lasts for this page. */ }
    if (value === 'yes') {
      banner.hidden = true;
      loadAnalytics();
    } else {
      // Reload removes any already loaded analytics code after withdrawing consent.
      if (document.getElementById('llmnews-ga4')) location.reload();
      else banner.hidden = true;
    }
  }

  document.getElementById('analytics-accept').addEventListener('click', () => save('yes'));
  document.getElementById('analytics-reject').addEventListener('click', () => save('no'));
  document.getElementById('analytics-settings').addEventListener('click', () => { banner.hidden = false; });
  if (choice === 'yes') loadAnalytics();
  else if (choice !== 'no') banner.hidden = false;
})();
