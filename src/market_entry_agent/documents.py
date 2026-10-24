"""Operator-selected local documents. Optional PDF adapter; no model-selected file reads."""
import csv
import hashlib
import io
import os
import sys
import shutil
import subprocess
from pathlib import Path


def extract(path, pdf_executable=None, timeout=40):
    path=Path(path).expanduser().resolve()
    if not path.is_file() or path.stat().st_size>8_000_000:raise ValueError('Document must be a file of at most 8 MB')
    raw=path.read_bytes();kind=path.suffix.lower()
    if kind=='.pdf':
        program=pdf_executable or shutil.which('pdftotext')
        adapter=os.environ.get('AGENT_PDF_ADAPTER_PYTHON','')
        if not program and not adapter:raise ValueError('Optional PDF adapter unavailable: configure AGENT_PDF_ADAPTER_PYTHON with pypdf or install Poppler pdftotext')
        # An explicit operator adapter, never a shell or model-supplied command.
        with __import__('tempfile').TemporaryDirectory() as folder:
            target=Path(folder)/'document.pdf';target.write_bytes(raw)
            code="import sys;from pypdf import PdfReader;r=PdfReader(sys.argv[1]);total=0;sys.stdout.reconfigure(encoding='utf-8');\nfor p in r.pages[:40]:\n t=p.extract_text() or '';total+=len(t);\n if total>1000000:raise ValueError('Text budget exceeded')\n print(t+'\\f',end='')"
            command=[str(program),'-layout','-enc','UTF-8','-f','1','-l','40',str(target),'-'] if program else [adapter,'-I','-c',code,str(target)]
            output=Path(folder)/'text.txt'
            try:
                with output.open('wb') as handle:
                    result=subprocess.run(command,stdout=handle,stderr=subprocess.DEVNULL,timeout=max(.01,min(40,timeout)),check=False)
            except (OSError,subprocess.TimeoutExpired):raise ValueError('PDF adapter unavailable or timed out') from None
            if result.returncode:raise ValueError('PDF extraction failed; scanned documents may require a separate OCR adapter')
            if output.stat().st_size>2_000_000:raise ValueError('Extracted PDF exceeds text budget')
            pages=output.read_text(encoding='utf-8').split('\f')
        chunks=[]
        for number,page in enumerate(pages,1):
            if not page.strip():continue
            for offset in range(0,len(page),24000):
                chunks.append((page[offset:offset+24000],{'format':'pdf','page':number,'page_offset':offset}))
        return raw,chunks
    if kind not in ('.csv','.tsv','.txt','.md'):raise ValueError('Supported documents: PDF (optional adapter), CSV, TSV, TXT, MD')
    body=raw.decode('utf-8-sig')
    if kind in ('.csv','.tsv'):
        rows=csv.reader(io.StringIO(body),delimiter='\t' if kind=='.tsv' else ',')
        header=next(rows,[])
        if not header or len(header)>80:raise ValueError('Table needs a header with at most eighty columns')
        chunks=[];batch=[];start=2;number=1
        for number,row in enumerate(rows,2):
            if number>10001:raise ValueError('Table exceeds ten thousand data rows')
            if len(row)!=len(header):raise ValueError('Table row width differs from header; preserve missing cells explicitly')
            line=' | '.join(str(key)+': '+str(value) for key,value in zip(header,row))
            if len(line)>20000:raise ValueError('Table row exceeds text budget')
            if sum(len(x)+1 for x in batch)+len(line)>24000:
                chunks.append(('\n'.join(batch),{'format':kind[1:],'row_start':start,'row_end':number-1,'columns':header}));batch=[];start=number
            batch.append(line)
        if batch:chunks.append(('\n'.join(batch),{'format':kind[1:],'row_start':start,'row_end':number,'columns':header}))
        return raw,chunks
    return raw,[(body[offset:offset+24000],{'format':kind[1:],'text_offset':offset}) for offset in range(0,len(body),24000)]


def ingest(store,path,metadata,pdf_executable=None,timeout=40):
    if not isinstance(metadata,dict) or any(not metadata.get(k) for k in ('title','url','countries','topics')):raise ValueError('Document metadata requires title, provenance URL, countries and topics')
    public=metadata.get('public',False)
    if type(public) is not bool:raise ValueError('Document public flag must be boolean')
    if not public and not store.evidence_path.is_relative_to(store.workspace):raise ValueError('Private documents cannot enter a shared evidence database')
    raw,chunks=extract(path,pdf_executable,timeout)
    if not chunks or len(chunks)>100:raise ValueError('Document needs 1–100 readable chunks; select a smaller document')
    checksum=hashlib.sha256(raw).hexdigest()
    records=[]
    for body,location in chunks:
        if not body.strip():continue
        records.append({'title':metadata['title'],'url':metadata['url'],'countries':metadata['countries'],'topics':metadata['topics'],
                        'published_at':metadata.get('published_at'),'body':body,'status':'source_claim','retrieval_kind':'document_text',
                        'document_location':location,'content_sha256':checksum,'visibility':'public' if public else 'private',
                        'extraction_limit':'PDF extraction covers pages 1–40; tables preserve cell text and row ranges; OCR is not implied.'})
    store.import_evidence({'schema':'field-evidence/v1','records':records})
    ids=[r['id'] for r in store.export_evidence()['records'] if r.get('content_sha256')==checksum and r.get('title')==metadata['title'] and r['url']==metadata['url']]
    return {'evidence_ids':ids,'chunks':len(records),'content_sha256':checksum,'visibility':'public' if public else 'private','model_calls':0}
