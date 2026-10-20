
const q = document.querySelector('#query');
const t = document.querySelector('#type');
const y = document.querySelector('#year');
const sort = document.querySelector('#sort');
const status = document.querySelector('#status');
const results = document.querySelector('#results');

let pages = [];
let visibleDocuments = 20;
const PAGE_SIZE = 20;

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
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
    output += '<mark>' + escapeHtml(text.slice(pos, pos + term.length)) + '</mark>';
    start = pos + term.length;
  }
  return output + escapeHtml(text.slice(start));
}

function excerptFor(page, term) {
  const body = page.text || '';
  if (!body) return page.needs_ocr ? 'No searchable text on this page (possibly scanned).' : 'No text preview available.';
  const at = term ? body.toLowerCase().indexOf(term) : -1;
  const start = at >= 0 ? Math.max(0, at - 100) : 0;
  const snippet = body.slice(start, start + 320);
  return (start ? '…' : '') + highlight(snippet, term) +
    (start + snippet.length < body.length ? '…' : '');
}


function pageLink(page, label) {
  const raw = String(page.url || page.source || '');
  let safeUrl;

  try {
    const parsed = new URL(raw, window.location.href);

    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return escapeHtml(label);
    }

    safeUrl = escapeHtml(parsed.href.split('#')[0]);
  } catch (_) {
    return escapeHtml(label);
  }

  const number = Number(page.page);
  const fragment = Number.isSafeInteger(number) && number > 0
    ? `#page=${number}`
    : '';

  return `<a href="${safeUrl}${fragment}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`;
}


function scorePage(page, term) {
  if (!term) return 0;

  const title = String(page.title || '').toLowerCase();
  const body = String(page.text || '').toLowerCase();
  const words = term.split(/\s+/).filter(Boolean);
  const combined = title + ' ' + body;

  let score = 0;

  if (title.includes(term)) score += 100;
  if (body.includes(term)) score += 50;

  for (const word of words) {
    if (title.includes(word)) score += 20;
    if (body.includes(word)) score += 5;
  }

  if (page.type === 'Minutes') score += 15;

  return score;
}
function search() {
  const term = q.value.trim().toLowerCase();
  const words = term.split(/\s+/).filter(Boolean);

const eligible = pages.filter(p =>
  (!t.value || p.type === t.value) &&
  (!y.value || p.year === y.value)
);

const allWords = eligible.filter(p => {
  const content = (String(p.title || '') + ' ' + String(p.text || '')).toLowerCase();
  return words.every(word => content.includes(word));
});

const matches = allWords.length || !words.length
  ? allWords
  : eligible.filter(p => {
      const content = (String(p.title || '') + ' ' + String(p.text || '')).toLowerCase();
      return words.some(word => content.includes(word));
    });

  const groups = new Map();
  for (const page of matches) {
    const key = page.source || page.url || `${page.title}|${page.year}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(page);
  }

  const documents = [...groups.values()].map(group => {
    group.sort((a, b) => Number(a.page) - Number(b.page));
    const ranked = [...group].sort((a, b) =>
      scorePage(b, term) - scorePage(a, term) || Number(a.page) - Number(b.page)
    );
    return {
      pages: group,
      ranked,
      score: scorePage(ranked[0], term),
      year: group[0].year || '',
      title: group[0].title || 'Untitled document'
    };
  });

    documents.sort((a, b) => {
    if (sort.value === 'newest') {
      return b.year.localeCompare(a.year) ||
        a.title.localeCompare(b.title);
    }

    if (sort.value === 'oldest') {
      return a.year.localeCompare(b.year) ||
        a.title.localeCompare(b.title);
    }

    if (sort.value === 'title') {
      return a.title.localeCompare(b.title);
    }

    if (term && b.score !== a.score) {
      return b.score - a.score;
    }

    return b.year.localeCompare(a.year) ||
      a.title.localeCompare(b.title);
  });
  status.textContent =
    `${documents.length.toLocaleString()} matching documents · ` +
    `${matches.length.toLocaleString()} matching pages · ` +
    `${pages.length.toLocaleString()} indexed pages`;

  results.innerHTML = documents.slice(0, visibleDocuments).map(doc => {
    const types = [...new Set(doc.pages.map(p => p.type).filter(Boolean))].join(', ');
    const top = doc.ranked.slice(0, 3);
    const previews = top.map(p => `
      <div style="margin:12px 0;padding-left:12px;border-left:3px solid #d6e0e6">
        <div>${pageLink(p, `Open page ${p.page}`)}</div>
        <p style="margin:6px 0">${excerptFor(p, term)}</p>
      </div>`).join('');

    const remaining = doc.ranked.slice(3);
    const more = remaining.length ? `
      <details style="margin-top:10px">
        <summary style="cursor:pointer;color:#006b90">
          Show ${remaining.length.toLocaleString()} more matching page${remaining.length === 1 ? '' : 's'}
        </summary>
        <div style="max-height:360px;overflow:auto;padding:8px 0">
          ${remaining.map(p => `<div style="margin:8px 0">${pageLink(p, `Page ${p.page}`)} · ${escapeHtml(p.type || 'Document')}</div>`).join('')}
        </div>
      </details>` : '';

    return `<article>
      <div><strong>${highlight(doc.title, term)}</strong></div>
      <div class="meta">${escapeHtml(doc.year || 'Year unknown')} ·
        ${escapeHtml(types || 'Document')} ·
        ${doc.pages.length.toLocaleString()} matching page${doc.pages.length === 1 ? '' : 's'}
      </div>
      ${previews}${more}
    </article>`;
  }).join('') || '<p>No results. Try a shorter search phrase or change the filters.</p>';

  let loadMore = document.querySelector('#load-more');
  if (!loadMore) {
    loadMore = document.createElement('button');
    loadMore.id = 'load-more';
    loadMore.type = 'button';
    loadMore.style.cssText = 'font:inherit;padding:12px 20px;border:1px solid #087d9f;border-radius:6px;background:#087d9f;color:white;cursor:pointer;margin:12px 0';
    loadMore.addEventListener('click', () => {
      visibleDocuments += PAGE_SIZE;
      search();
    });
    results.after(loadMore);
  }
  const remainingDocs = documents.length - visibleDocuments;
  loadMore.hidden = remainingDocs <= 0;
  if (remainingDocs > 0) {
    loadMore.textContent = `Show more documents (${remainingDocs.toLocaleString()} remaining)`;
  }
}


Promise.all([
  fetch('records.json').then(r => {
    if (!r.ok) throw Error('CDD index unavailable');
    return r.json();
  }),
  fetch('drive-records.json').then(r => {
    if (!r.ok) throw Error('Google Drive index unavailable');
    return r.json();
  })
])
  .then(([cddData, driveData]) => {
    const cddPages = cddData.pages || [];
    const drivePages = (driveData.pages || []).map(p => ({
      ...p,
      title: p.title || p.source || 'Additional Public Record',
      type: 'Additional Public Records',
      year: String(p.year || ''),
      source: `Additional Public Records: ${p.source || 'Document'}`
    }));

    pages = [...cddPages, ...drivePages];

    document.querySelector('#updated').textContent =
      cddData.updated ? `Last indexed: ${cddData.updated}` : '';

    [...new Set(pages.map(p => p.year).filter(Boolean))]
      .sort().reverse().forEach(year => {
        const option = document.createElement('option');
        option.value = option.textContent = year;
        y.appendChild(option);
      });

    if (![...t.options].some(option =>
      option.value === 'Additional Public Records'
    )) {
      const option = document.createElement('option');
      option.value = 'Additional Public Records';
      option.textContent = 'Additional Public Records';
      t.appendChild(option);
    }

    search();
  })
  .catch(error => {
    console.error('Archive loading error:', error);
    status.textContent =
      'The archive could not be loaded. Please try again later.';
  });


[q, t, y].forEach(el => el.addEventListener('input', () => {
  visibleDocuments = PAGE_SIZE;
  search();
}));
