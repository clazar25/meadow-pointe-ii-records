"""Polite, bounded crawler of public MP2 CDD document pages. No login or bypass."""
import hashlib,json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse,urldefrag
import fitz,requests
from bs4 import BeautifulSoup

ROOT='https://meadowpointe2cdd.org'
START=[ROOT+'/documents',ROOT+'/meetings']
OUTPUT=Path('records.json')
MAX_HTML=300
MAX_PDFS=500
MAX_PDF_BYTES=25*1024*1024
session=requests.Session()
session.headers['User-Agent']='MeadowPointeIIResidentArchive/1.0 (public record index; contact via GitHub repository)'

def is_cdd_page(url):
    p=urlparse(url)
    return p.scheme=='https' and p.netloc.lower() in ('meadowpointe2cdd.org','www.meadowpointe2cdd.org')

def pdf_link(url):
    return urlparse(url).path.lower().endswith('.pdf')

def classify_page(text, document_type):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    heading = ' '.join(lines[:8]).lower()

    # Identify meeting minutes by their headings.
    minutes_heading = (
        re.search(r'\b(meeting|workshop)\s+minutes\b', heading)
        or re.search(r'\bminutes\s+of\s+(the\s+)?', heading)
        or re.search(r'\b(draft|approved)\s+minutes\b', heading)
    )

    if minutes_heading:
        return 'Minutes'

    # Identify actual agenda pages.
    if re.search(r'\b(meeting|workshop)\s+agenda\b', heading):
        return 'Agenda'

    # Keep separately published minutes categorized as minutes.
    if document_type == 'Minutes':
        return 'Minutes'

    return 'Supporting Documents'
    
def classify_document(title, filename):
    name = (title + ' ' + filename).lower()

    if 'minute' in name:
        return 'Minutes'
    if 'agenda' in name:
        return 'Agenda'
    return 'Other'


queue=list(START);visited=set();pdfs={}
while queue and len(visited)<MAX_HTML:
    url=queue.pop(0)
    if url in visited or not is_cdd_page(url):continue
    visited.add(url)
    try:
        response=session.get(url,timeout=25)
        response.raise_for_status()
        if 'html' not in response.headers.get('Content-Type','').lower():continue
        soup=BeautifulSoup(response.text,'html.parser')
        for link in soup.select('a[href]'):
            target=urldefrag(urljoin(url,link['href']))[0]
            if urlparse(target).scheme not in ('http','https'):continue
            label=link.get_text(' ',strip=True) or target.rsplit('/',1)[-1]
            if pdf_link(target):pdfs.setdefault(target,label)
            elif is_cdd_page(target) and target not in visited and any(k in urlparse(target).path.lower() for k in ('document','meeting','agenda','minute','archive','fiscal','board','packet')):
                if target not in queue:queue.append(target)
    except requests.RequestException as exc:print('Page skipped:',url,exc)
    time.sleep(.15)

previous=json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {'pages':[]}
old_by_url={}
for item in previous.get('pages',[]):old_by_url.setdefault(item['source'],[]).append(item)
indexed=[];errors=0
for url,title in list(pdfs.items())[:MAX_PDFS]:
    try:
        with session.get(url,timeout=40,stream=True) as response:
            response.raise_for_status()
            data=bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data)>MAX_PDF_BYTES:raise ValueError('PDF exceeds size limit')
        if not data.startswith(b'%PDF'):continue
        digest=hashlib.sha256(data).hexdigest()
        old=old_by_url.get(url,[])
        if old and old[0].get('sha256')==digest:
            for item in old:
                updated = item.copy()
                updated['type'] = classify_page(
                    updated.get('text', ''),
                    classify_document(updated.get('title', title), urlparse(url).path.rsplit('/', 1)[-1])
                )
                indexed.append(updated)
            continue
        doc=fitz.open(stream=bytes(data),filetype='pdf')
        filename=urlparse(url).path.rsplit('/',1)[-1]
        combined=(title+' '+filename).lower()
        kind=classify_document(title, filename)
        years=re.findall(r'20(?:1\d|2\d|3\d)',combined)
        year=years[0] if years else ''
        for number,page in enumerate(doc,1):
            text=page.get_text(sort=True).strip()
            indexed.append({'source':url,'url':url,'title':title,'type':classify_page(text, kind),'year':year,'page':number,'text':text[:25000],'sha256':digest,'needs_ocr':not bool(text)})
        print('Indexed',title,len(doc),'pages')
    except (requests.RequestException,ValueError,RuntimeError) as exc:
        errors+=1;print('PDF skipped:',url,exc)
        indexed.extend(old_by_url.get(url,[]))
    time.sleep(.2)
# Keep historical records if they disappear from the official site's links.
found=set(pdfs)
for url,items in old_by_url.items():
    if url not in found:indexed.extend(items)
if not pdfs:
    raise SystemExit('No PDFs found; refusing to overwrite the prior index. Check site structure and crawler logs.')
# Group pages from the same PDF.
by_source = {}
for item in indexed:
    by_source.setdefault(item['source'], []).append(item)

for pages in by_source.values():
    pages.sort(key=lambda p: p['page'])

    for item in pages:
        # Keep the classification determined from each page.
        # Do not assume that every following page is minutes.
        item['type'] = item.get('type', 'Supporting Documents')
indexed.sort(key=lambda p:(p.get('year',''),p['title'],p['page']),reverse=True)
OUTPUT.write_text(json.dumps({'updated':datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),'pages':indexed},ensure_ascii=False,separators=(',',':')))
print('Indexed',len(indexed),'pages across',len(set(x['source'] for x in indexed)),'PDFs; failures',errors)
