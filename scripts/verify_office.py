"""Opt-in real local Office roundtrip; synthetic data, no model or publishing."""
import importlib
import json
import os
from pathlib import Path
import tempfile
from openpyxl import Workbook
from pptx import Presentation

MODULE='market_entry_agent'
core=importlib.import_module(MODULE+'.core')
product=importlib.import_module(MODULE+'.product')
office=importlib.import_module(MODULE+'.office')
documents=importlib.import_module(MODULE+'.documents')
with tempfile.TemporaryDirectory(prefix='office 中文 ') as folder:
 root=Path(folder);store=core.Store(root/'workspace')
 report=core.Agent(store,product.SPEC).run(dict(product.SPEC['starter']),'demo')['report']
 word=root/'研究报告.docx';receipt=office.export_docx(report,word)
 book=Workbook();sheet=book.active;sheet.append(['Fictional quote','USD']);sheet.append(['Product A',100]);book.save(root/'报价.xlsx');book.close()
 slides=Presentation();slide=slides.slides.add_slide(slides.slide_layouts[1]);slide.shapes.title.text='Fictional public briefing';slide.placeholders[1].text='Synthetic route; no actual customer';slides.save(root/'简报.pptx')
 results=[]
 for name,expected in [('研究报告.docx',report['title']),('报价.xlsx','Product A'),('简报.pptx','Fictional public briefing')]:
  raw,chunks=documents.extract(root/name)
  assert expected in ''.join(text for text,_ in chunks),name
  metadata=dict(title='Fictional '+name,url='https://example.org/'+Path(name).suffix[1:],countries=['Vietnam'],topics=['trade'])
  imported=documents.ingest(store,root/name,metadata)
  assert imported['visibility']=='private' and imported['evidence_ids']
  results.append(dict(format=Path(name).suffix,private_import=True,chunks=len(chunks)))
 assert receipt['model_calls']==0
 assert store.get_run(store.list_runs()[0]['id'])['report']==report
 print(json.dumps(dict(word_export='complete text verified',imports=results,report_unchanged=True,model_calls=0),ensure_ascii=False))
