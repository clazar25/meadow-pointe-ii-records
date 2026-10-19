
const q = document.querySelector('#query');
const t = document.querySelector('#type');
const y = document.querySelector('#year');
const status = document.querySelector('#status');
const results = document.querySelector('#results');

let pages = [];

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[c]));
}

function highlight(text, term) {
  if (!term) return escapeHtml(text);

  const lower = text.toLowerCase();
  const search = term.toLowerCase();
  let output = '';
  let start = 0;
  let pos;

  while ((pos = lower.indexOf(search, start)) !== -1) {
    output += escapeHtml(text.slice(start, pos));
    output += '<mark>' +
      escapeHtml(text.slice(pos, pos + term.length)) +
      '</mark>';
    start = pos + term.length;
  }

  return output + escapeHtml(text.slice(start));
}

function search() {
  const term = q.value.trim().toLowerCase();

  let hits = pages.filter(p =>
    (!t.value || p.type === t.value) &&
    (!y.value || p.year === y.value) &&
    (!term || (p.title + ' ' + p.text).toLowerCase().includes(term))
  );

  if (term) {
    hits.sort((a, b) => {
      const score = p => {
        const title = p.title.toLowerCase();
        const body = p.text.toLowerCase();
        const titleMatches = title.split(term).length - 1;
        const textMatches = body.split(term).length - 1;

        return titleMatches * 10 + textMatches;
      };

      return score(b) - score(a);
    });
  }

  status.textContent =
    `${hits.length} matching pages from ${pages.length} indexed pages`;

  results.innerHTML = hits.slice(0, 100).map(p => {
    const body = p.text || '';
    const at = term ? body.toLowerCase().indexOf(term) : -1;
    const start = Math.max(0, at - 100);
    const excerpt = body.slice(start, start + 320);

    return `
      <article>
        <a href="${escapeHtml(p.url)}#page=${p.page}"
           target="_blank" rel="noopener noreferrer">
          <strong>${highlight(p.title, term)}</strong>
          (page ${p.page})
        </a>
        <div class="meta">
          ${escapeHtml(p.type)} ·
          ${escapeHtml(p.year || 'Year unknown')}
        </div>
        <p>
          ${highlight(excerpt, term)}
          ${body.length > start + excerpt.length ? '…' : ''}
        </p>
      </article>
    `;
  }).join('') || '<p>No results. Try a shorter search phrase.</p>';
}

fetch('records.json')
  .then(r => {
    if (!r.ok) throw Error('Index unavailable');
    return r.json();
  })
  .then(data => {
    pages = data.pages || [];

    document.querySelector('#updated').textContent =
      data.updated ? `Last indexed: ${data.updated}` : '';

    [...new Set(pages.map(p => p.year).filter(Boolean))]
      .sort()
      .reverse()
      .forEach(year => {
        const option = document.createElement('option');
        option.value = option.textContent = year;
        y.appendChild(option);
      });

    search();
  })
  .catch(() => {
    status.textContent =
      'The archive could not be loaded. Please try again later.';
  });

[q, t, y].forEach(el => el.addEventListener('input', search));
