"""Editable DOCX from a saved report, with no model call or optional runtime."""
import hashlib
import io
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
ET.register_namespace('w',W)


def node(parent,name,attributes=None,text=None):
    result=ET.SubElement(parent,'{'+W+'}'+name,{'{'+W+'}'+k:str(v) for k,v in (attributes or {}).items()})
    if text is not None:result.text=text
    return result


def clean(value):
    # XML 1.0 permits tab/newline/CR but not other control characters.
    return ''.join(c for c in value if c in '\t\n\r' or '\u0020'<=c<='\ud7ff' or '\ue000'<=c<='\ufffd' or '\U00010000'<=c<='\U0010ffff')


def docx_bytes(report):
    from .core import markdown
    source=markdown(report)
    if len(source)>240000:raise ValueError('Report exceeds Word export text budget; use Markdown export')
    if len(source.splitlines())>8000:raise ValueError('Report has too many paragraphs; use Markdown export')
    doc=ET.Element('{'+W+'}document');body=node(doc,'body');preserved=[]
    code=False
    for line in source.splitlines():
        style=None;number=None;content=line
        if line.startswith('```'):code=not code
        if not code and not line.startswith('```'):
            heading=re.match(r'^(#{1,6})\s+(.*)$',line)
            bullet=re.match(r'^\s*[-*]\s+(.*)$',line)
            ordered=re.match(r'^\s*\d+[.)]\s+(.*)$',line)
            if heading:style='Heading'+str(min(3,len(heading[1])));content=heading[2]
            elif bullet:style='ListParagraph';number=1;content=bullet[1]
            elif ordered:style='ListParagraph';content=line  # Preserve explicit numbers instead of renumbering them.
        p=node(body,'p');properties=node(p,'pPr')
        if style:node(properties,'pStyle',{'val':style})
        if number:
            numbering=node(properties,'numPr');node(numbering,'ilvl',{'val':0});node(numbering,'numId',{'val':number})
        run=node(p,'r');t=node(run,'t',text=clean(content));t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');preserved.append(clean(content))
    section=node(body,'sectPr');node(section,'pgSz',{'w':11906,'h':16838});node(section,'pgMar',{'top':1440,'right':1440,'bottom':1440,'left':1440})
    styles=ET.Element('{'+W+'}styles')
    for sid,size,bold in [('Normal',22,False),('Heading1',34,True),('Heading2',28,True),('Heading3',24,True),('ListParagraph',22,False)]:
        st=node(styles,'style',{'type':'paragraph','styleId':sid});node(st,'name',{'val':sid})
        if sid!='Normal':node(st,'basedOn',{'val':'Normal'})
        props=node(st,'pPr');node(props,'spacing',{'after':120,'line':300,'lineRule':'auto'})
        if sid.startswith('Heading'):node(props,'outlineLvl',{'val':int(sid[-1])-1})
        rp=node(st,'rPr');node(rp,'rFonts',{'ascii':'Calibri','hAnsi':'Calibri','eastAsia':'Microsoft YaHei'});node(rp,'sz',{'val':size})
        if bold:node(rp,'b')
    numbering=ET.Element('{'+W+'}numbering')
    for nid,fmt,label in [(1,'bullet','•'),(2,'decimal','%1.')]:
        abstract=node(numbering,'abstractNum',{'abstractNumId':nid});level=node(abstract,'lvl',{'ilvl':0});node(level,'start',{'val':1});node(level,'numFmt',{'val':fmt});node(level,'lvlText',{'val':label});ppr=node(level,'pPr');node(ppr,'ind',{'left':480,'hanging':240})
        num=node(numbering,'num',{'numId':nid});node(num,'abstractNumId',{'val':nid})
    declarations='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    content_types=declarations+'''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/></Types>'''
    rels=declarations+'''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'''
    document_rels=declarations+'''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/></Relationships>'''
    target=io.BytesIO()
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml',content_types);archive.writestr('_rels/.rels',rels);archive.writestr('word/_rels/document.xml.rels',document_rels)
        for name,element in [('document',doc),('styles',styles),('numbering',numbering)]:archive.writestr('word/'+name+'.xml',ET.tostring(element,encoding='utf-8',xml_declaration=True))
    # Compare the text written to the saved report representation, without re-analysis.
    actual='\n'.join(t.text or '' for t in doc.iter('{'+W+'}t'))
    if actual!='\n'.join(preserved):raise ValueError('Word export text preservation check failed')
    return target.getvalue()


def export_docx(report,output):
    destination=Path(output).expanduser().absolute()
    if destination.suffix.lower()!='.docx' or destination.exists():raise ValueError('Choose a new .docx output file; existing files are never overwritten')
    raw=docx_bytes(report);destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('xb') as handle:handle.write(raw)
    return {'saved':str(destination),'format':'docx','adapter':'builtin-docx','model_calls':0,'content_sha256':hashlib.sha256(raw).hexdigest(),
            'note':'Saved report text with editable headings and lists. Complex Markdown tables and inline notation remain text; no model rewrite.'}
