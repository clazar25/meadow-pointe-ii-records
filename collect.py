"""Index publicly linked Meadow Pointe II CDD PDFs, preserving historical records."""
import hashlib
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import fitz
import requests
from bs4 import BeautifulSoup

ROOT = 'https://meadowpointe2cdd.org'
START = [ROOT + '/documents', ROOT + '/meetings']
OUTPUT = Path('records.json')
MAX_HTML = 300
MAX_PDFS = 500
MAX_PDF_BYTES = 25 * 1024 * 1024

session = requests.Session()
session.headers['User-Agent'] = (
    'MeadowPointeIIResidentArchive/1.0 (public record index; contact via GitHub repository)'
)


def is_cdd_page(url):
    parsed = urlparse(url)
    return parsed.scheme == 'https' and parsed.netloc.lower() in (
        'meadowpointe2cdd.org', 'www.meadowpointe2cdd.org'
    )


def pdf_link(url):
    return urlparse(url).path.lower().endswith('.pdf')


def classify_document(title, filename):
    """Classify a PDF by its name only when the name is unambiguous."""
    name = (title + ' ' + filename).lower()
    if re.search(r'\bminutes?\b', name) and not re.search(r'\bagenda\b|\bpacket\b', name):
        return 'Minutes'
    if re.search(r'\bagenda\b', name):
        return 'Agenda'
    return 'Supporting Documents'


# Strong headings only: "approval of minutes" in an agenda is NOT minutes.
MINUTES_HEADER = re.compile(
    r'(?i)^(?:(?:draft|approved|final|regular|special|workshop|board|meeting)\s+){0,4}'
    r'(?:meeting\s+)?minutes(?:\s+of\b.*)?$'
    r'|^minutes\s+of\s+(?:the\s+)?(?:regular|special|workshop|board|meeting|\w+\s+)' 
    r'.{0,90}$'
    r'|^(?:regular|special|workshop|board)\s+(?:meeting\s+)?minutes\b.*$'
)
AGENDA_HEADER = re.compile(
    r'(?i)^(?:(?:regular|special|workshop|board|final|draft)\s+){0,4}'
    r'(?:meeting\s+)?agenda(?:\s+and\s+packet)?$'
    r'|^(?:regular|special|workshop|board)\s+meeting\s+agenda\b.*$'
    r'|^agenda\s+for\s+(?:the\s+)?(?:regular|special|workshop|board)\b.*$'
)
NEW_DOCUMENT_HEADER = re.compile(
    r'(?i)^(?:financial statements?|balance sheet|statement of revenues.*|'
    r'(?:district\s+)?(?:engineer|manager|attorney).{0,12}report|'
    r'landscap(?:e|ing)\s+(?:proposal|bid)|bid proposal|'
    r'resolution\s+(?:no\.?\s*)?\d|certificate of insurance|'
    r'proposed budget|budget amendment|request for proposals|'
    r'exhibit\s+[a-z0-9]+)$'
)
MINUTES_END = re.compile(
    r'(?i)there\s+being\s+no\s+further\s+business|'
    r'respectfully\s+submitted|secretary\s*/\s*assistant\s+secretary'
)


def page_signals(text):
    """Inspect likely document headings, not arbitrary mentions inside body text."""
    lines = [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines() if line.strip()]
    # PDF headers may have the CDD name, date and meeting title before the heading.
    top = lines[:14]
    # Check single lines and short combinations to accommodate wrapped headings.
    candidates = list(top)
    candidates.extend(top[i] + ' ' + top[i + 1] for i in range(len(top) - 1))
    minute = any(MINUTES_HEADER.fullmatch(line) for line in candidates)
    agenda = any(AGENDA_HEADER.fullmatch(line) for line in candidates)
    new_document = any(NEW_DOCUMENT_HEADER.fullmatch(line) for line in top[:8])
    return minute, agenda, new_document


def classify_pages(pages):
    """Classify all pages of one PDF, including pages retained from prior runs.

    Do not mistake an agenda's 'approval of minutes' item for actual minutes.
    Once a clear minutes heading is found, include continuation pages until a
    closing/signature page or the start of a recognizable different document.
    """
    if not pages:
        return
    pages.sort(key=lambda item: int(item.get('page', 0)))
    source = pages[0].get('source', '')
    filename = urlparse(source).path.rsplit('/', 1)[-1]
    document_type = classify_document(pages[0].get('title', ''), filename)
    minutes_active = False
    agenda_active = False

    for index, item in enumerate(pages):
        body = item.get('text', '') or ''
        minute_start, agenda_start, new_document = page_signals(body)

        if document_type == 'Minutes':
            item['type'] = 'Minutes'
            continue

        if minute_start:
            minutes_active = True
            agenda_active = False
        elif agenda_start:
            minutes_active = False
            agenda_active = True
        elif new_document:
            minutes_active = False
            agenda_active = False

        if minutes_active:
            item['type'] = 'Minutes'
        elif agenda_active:
            item['type'] = 'Agenda'
        elif document_type == 'Agenda' and index == 0 and not new_document:
            # Many combined packets have an agenda first page without a standalone heading.
            item['type'] = 'Agenda'
        else:
            item['type'] = 'Supporting Documents'

        if minutes_active and MINUTES_END.search(body[-3000:]):
            minutes_active = False
        # Agenda pages generally occupy the beginning of a packet. Stop the
        # agenda section when its numbered items end or a new document starts.
        if agenda_active and (
            re.search(r'(?i)\b(?:adjournment|next\s+meeting|meeting\s+adjourned)\b', body[-1600:])
            or new_document
        ):
            agenda_active = False


def crawl_pdf_links():
    queue = list(START)
    visited = set()
    pdfs = {}
    while queue and len(visited) < MAX_HTML:
        url = queue.pop(0)
        if url in visited or not is_cdd_page(url):
            continue
        visited.add(url)
        try:
            response = session.get(url, timeout=25)
            response.raise_for_status()
            if 'html' not in response.headers.get('Content-Type', '').lower():
                continue
            soup = BeautifulSoup(response.text, 'html.parser')
            for link in soup.select('a[href]'):
                target = urldefrag(urljoin(url, link['href']))[0]
                if urlparse(target).scheme not in ('http', 'https'):
                    continue
                label = link.get_text(' ', strip=True) or target.rsplit('/', 1)[-1]
                if pdf_link(target):
                    pdfs.setdefault(target, label)
                elif (is_cdd_page(target) and target not in visited and
                      any(part in urlparse(target).path.lower() for part in (
                          'document', 'meeting', 'agenda', 'minute', 'archive',
                          'fiscal', 'board', 'packet'
                      ))):
                    if target not in queue:
                        queue.append(target)
        except requests.RequestException as exc:
            print('Page skipped:', url, exc)
        time.sleep(.15)
    return pdfs


def main():
    pdfs = crawl_pdf_links()
    if not pdfs:
        raise SystemExit('No PDFs found; refusing to overwrite the prior index.')

    previous = json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {'pages': []}
    old_by_url = defaultdict(list)
    for item in previous.get('pages', []):
        old_by_url[item['source']].append(item)

    indexed = []
    errors = 0
    for url, title in list(pdfs.items())[:MAX_PDFS]:
        old = old_by_url.get(url, [])
        try:
            with session.get(url, timeout=40, stream=True) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > MAX_PDF_BYTES:
                        raise ValueError('PDF exceeds size limit')
            if not data.startswith(b'%PDF'):
                indexed.extend(old)
                continue
            digest = hashlib.sha256(data).hexdigest()
            if old and old[0].get('sha256') == digest:
                indexed.extend(old)
                continue

            doc = fitz.open(stream=bytes(data), filetype='pdf')
            filename = urlparse(url).path.rsplit('/', 1)[-1]
            years = re.findall(r'20(?:1\d|2\d|3\d)', (title + ' ' + filename).lower())
            year = years[0] if years else ''
            for number, page in enumerate(doc, 1):
                text = page.get_text(sort=True).strip()
                indexed.append({
                    'source': url, 'url': url, 'title': title,
                    'type': 'Supporting Documents', 'year': year,
                    'page': number, 'text': text[:25000], 'sha256': digest,
                    'needs_ocr': not bool(text)
                })
            print('Indexed', title, len(doc), 'pages')
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            errors += 1
            print('PDF skipped:', url, exc)
            indexed.extend(old)
        time.sleep(.2)

    # Preserve historical pages even if their PDF links vanish from the CDD website.
    found = set(pdfs)
    for url, items in old_by_url.items():
        if url not in found:
            indexed.extend(items)

    by_source = defaultdict(list)
    for item in indexed:
        by_source[item['source']].append(item)
    for pages in by_source.values():
        classify_pages(pages)

    indexed.sort(key=lambda item: (item.get('year', ''), item['title'], item['page']), reverse=True)
    # Never silently replace a populated archive with an empty or much smaller one.
    old_count = len(previous.get('pages', []))
    if old_count and len(indexed) < old_count:
        raise SystemExit(
            f'Refusing to reduce archive from {old_count} to {len(indexed)} pages; '
            'check the crawler before updating records.json.'
        )
    OUTPUT.write_text(json.dumps({
        'updated': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        'pages': indexed
    }, ensure_ascii=False, separators=(',', ':')))
    print('Indexed', len(indexed), 'pages across', len(by_source), 'PDFs; failures', errors)


if __name__ == '__main__':
    main()
