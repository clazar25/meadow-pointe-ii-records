
const q = document.querySelector('#query');
const t = document.querySelector('#type');
const y = document.querySelector('#year');
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
    const parsed = new URL(raw);
    if (!['http:', 'https:'].includes(parsed.protocol)) return escapeHtml(label);
    safeUrl = escapeHtml(parsed.href.split('#')[0]);
  } catch (_) {
    return escapeHtml(label);
  }
  const number = Number(page.page);
  const fragment = Number.isSafeInteger(number) && number > 0 ? `#page=${number}` : '';
  return `<a href="${safeUrl}${fragment}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`;
}

function scorePage(page, term) {
  if (!term) return 0;
  const title = String(page.title || '').toLowerCase();
  const body = String(page.text || '').toLowerCase();
  return (title.split(term).length - 1) * 10 + (body.split(term).length - 1);
}

function search() {
  const term = q.value.trim().toLowerCase();
  const matches = pages.filter(p =>
    (!t.value || p.type === t.value) &&
    (!y.value || p.year === y.value) &&
    (!term || (String(p.title || '') + ' ' + String(p.text || '')).toLowerCase().includes(term))
  );

  
  // Group identical PDFs using their SHA-256 fingerprints.
  // Keep the original archive unchanged.
  const groups = new Map();

  for (const page of matches) {
    const key = page.sha256
      ? `sha256:${page.sha256}`
      : `source:${page.source || page.url || `${page.title}|${page.year}`}`;

    if (!groups.has(key)) groups.set(key, new Map());

    const group = groups.get(key);
    const number = Number(page.page);
    const pageKey = Number.isSafeInteger(number) && number > 0
      ? `page:${number}`
      : `unknown:${page.source || page.url || ''}:${page.text || ''}`;

    if (!group.has(pageKey)) group.set(pageKey, page);
  }

  const uniqueMatches = [...groups.values()]
    .reduce((sum, group) => sum + group.size, 0);

  const documents = [...groups.values()].map(pageMap => {
    const group = [...pageMap.values()];

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
    if (term && b.score !== a.score) return b.score - a.score;
    return b.year.localeCompare(a.year) || a.title.localeCompare(b.title);
  });

  status.textContent =
    `${documents.length.toLocaleString()} matching documents · ` +
    `${uniqueMatches.toLocaleString()} matching pages · ` +
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
      .sort().reverse().forEach(year => {
        const option = document.createElement('option');
        option.value = option.textContent = year;
        y.appendChild(option);
      });
    search();
  })
  .catch(() => {
    status.textContent = 'The archive could not be loaded. Please try again later.';
  });

[q, t, y].forEach(el => el.addEventListener('input', () => {
  visibleDocuments = PAGE_SIZE;
  search();
}));
