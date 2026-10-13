"""Polite, bounded crawler of public MP2 CDD document pages. No login or bypass."""
import hashlib,json,re,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse,urldefrag
import fitz,requests
from bs4 import BeautifulSoup

ROOT='https://www.meadowpointe2cdd.org'
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
            indexed.extend(old);continue
        doc=fitz.open(stream=bytes(data),filetype='pdf')
        filename=urlparse(url).path.rsplit('/',1)[-1]
        combined=(title+' '+filename).lower()
        kind='Minutes' if 'minute' in combined else 'Agenda' if 'agenda' in combined else 'Other'
        years=re.findall(r'20(?:1\d|2\d|3\d)',combined)
        year=years[0] if years else ''
        for number,page in enumerate(doc,1):
            text=page.get_text(sort=True).strip()
            indexed.append({'source':url,'url':url,'title':title,'type':kind,'year':year,'page':number,'text':text[:25000],'sha256':digest,'needs_ocr':not bool(text)})
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
indexed.sort(key=lambda p:(p.get('year',''),p['title'],p['page']),reverse=True)
OUTPUT.write_text(json.dumps({'updated':datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),'pages':indexed},ensure_ascii=False,separators=(',',':')))
print('Indexed',len(indexed),'pages across',len(set(x['source'] for x in indexed)),'PDFs; failures',errors)
