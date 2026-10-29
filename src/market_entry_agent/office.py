"""Explicit local document adapters; trusted operator programs, never model commands."""
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import time
import zipfile
import xml.etree.ElementTree as ET

def executable(variable):
    value=os.environ.get(variable,'')
    path=Path(value).expanduser()
    if not value or not path.is_absolute() or not path.is_file():
        raise ValueError('Configure '+variable+' as an absolute executable path')
    return str(path.absolute())

def process_env():
    keys=('PATH','HOME','USERPROFILE','SYSTEMROOT','WINDIR','TEMP','TMP','TMPDIR','LANG','LC_ALL','DOTNET_ROOT')
    env={k:v for k,v in os.environ.items() if k.upper() in keys}
    env.update(OFFICECLI_NO_AUTO_RESIDENT='1',OFFICECLI_SKIP_UPDATE='1',PYTHONIOENCODING='utf-8')
    return env

def invoke(command, timeout=40, cwd=None):
    with tempfile.TemporaryFile() as output:
        try:
            result=subprocess.run(command,stdout=output,stderr=subprocess.DEVNULL,
                                  timeout=max(.01,min(60,timeout)),env=process_env(),cwd=cwd,check=False)
        except (OSError,subprocess.TimeoutExpired):
            raise ValueError('Local document adapter unavailable or timed out') from None
        if result.returncode:raise ValueError('Local document adapter failed; check its installation and format support')
        size=output.tell()
        if size>2_000_000:raise ValueError('Document adapter output exceeds 2 MB')
        output.seek(0)
        return output.read().decode('utf-8')

def office_chunks(raw, suffix, timeout=40):
    # Bound compressed containers before giving data to an optional converter.
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files=archive.infolist()
            if len(files)>2000 or sum(f.file_size for f in files)>32_000_000:
                raise ValueError('Office document exceeds expanded size budget')
            for f in files:
                if f.filename.startswith('/') or '..' in f.filename.split('/') or f.flag_bits & 1:
                    raise ValueError('Unsupported Office container entry')
    except zipfile.BadZipFile:
        raise ValueError('Office input must be a valid DOCX, XLSX or PPTX container') from None
    program=executable('AGENT_DOCUMENT_ADAPTER_PYTHON')
    code=("import sys,io;from markitdown import MarkItDown;"
          "sys.stdout.reconfigure(encoding='utf-8');"
          "r=MarkItDown(enable_plugins=False).convert_stream(io.BytesIO(sys.stdin.buffer.read()),file_extension=sys.argv[1]);"
          "print(r.text_content,end='')")
    with tempfile.TemporaryDirectory() as folder:
        input_path=Path(folder)/('input'+suffix)
        input_path.write_bytes(raw)
        # Fixed isolated script reads stdin; input cannot be interpreted as a URL or command.
        with input_path.open('rb') as source, tempfile.TemporaryFile() as output:
            try:
                result=subprocess.run([program,'-I','-c',code,suffix],stdin=source,stdout=output,
                                      stderr=subprocess.DEVNULL,timeout=max(.01,min(40,timeout)),
                                      env=process_env(),cwd=folder,check=False)
            except (OSError,subprocess.TimeoutExpired):raise ValueError('Office import unavailable or timed out') from None
            if result.returncode:raise ValueError('Office import failed; install the optional MarkItDown format extras')
            if output.tell()>1_000_000:raise ValueError('Converted document exceeds text budget')
            output.seek(0);text=output.read().decode('utf-8')
    return [(text[i:i+24000],dict(format=suffix[1:],adapter='markitdown',text_offset=i,
             location_note='Converted text offsets; original pages, cells and slide positions are not certified.'))
            for i in range(0,len(text),24000)]

def export_docx(report, output, timeout=60):
    if not os.environ.get('AGENT_OFFICECLI'):
        from .report_document import export_docx as builtin_export
        return builtin_export(report,output)
    from .core import markdown
    program=executable('AGENT_OFFICECLI')
    destination=Path(output).expanduser().absolute()
    if destination.suffix.lower()!='.docx' or destination.exists():
        raise ValueError('Choose a new .docx output file; existing files are never overwritten')
    text=markdown(report)
    if len(text)>240000:raise ValueError('Report exceeds Office export text budget; use Markdown export')
    destination.parent.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    with tempfile.TemporaryDirectory(dir=destination.parent) as folder:
        target=Path(folder)/'report.docx'
        def call(*args):
            return invoke([program,*args],timeout-(time.monotonic()-start),folder)
        call('create',str(target))
        # Keep the complete saved report, with no model rewrite or added claims.
        for i in range(0,len(text),6000):
            if time.monotonic()-start>=timeout:raise ValueError('Office export time budget exhausted')
            call('add',str(target),'/body','--type','paragraph','--prop','text='+text[i:i+6000])
        with zipfile.ZipFile(target) as archive:
            doc=ET.fromstring(archive.read('word/document.xml'))
            actual=''.join(node.text or '' for node in doc.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'))
        # Newlines become paragraph breaks. Detect silently missing report text.
        normalize=lambda value: ''.join(value.split())
        if normalize(text)!=normalize(actual):raise ValueError('Office export did not preserve the complete report text')
        raw=target.read_bytes()
        # Exclusive creation also handles another process creating the output during export.
        with destination.open('xb') as handle:handle.write(raw)
    return dict(saved=str(destination),format='docx',adapter='iOfficeAI/OfficeCLI',
                content_sha256=hashlib.sha256(raw).hexdigest(),model_calls=0,
                note='Editable text report; Markdown notation is retained, not a typeset template.')
