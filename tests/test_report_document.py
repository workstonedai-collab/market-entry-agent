"""Read the generated Office package and retain saved text without another model."""
import importlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
import zipfile

MODULE='market_entry_agent'
core=importlib.import_module(MODULE+'.core');SPEC=importlib.import_module(MODULE+'.product').SPEC
document=importlib.import_module(MODULE+'.report_document')
office=importlib.import_module(MODULE+'.office')


class ReportDocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=core.Store(Path(self.tmp.name)/'报告')
        run=core.Agent(self.store,SPEC).run(dict(question='Synthetic report for export.',countries=['Vietnam'],topics=['trade'],max_steps=8),'demo')
        self.report=run['report'];self.assertIsNotNone(self.report)

    def test_readable_docx_has_headings_lists_sources_and_no_external_relationships(self):
        self.report['title']='标题 <>& 引用';self.report['actions']=['3. Preserve the original number.','Source-linked next check.']
        with patch.object(core.Model,'next',side_effect=AssertionError('Export must not call a model')):raw=document.docx_bytes(self.report)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertIsNone(archive.testzip());names=archive.namelist();self.assertIn('word/styles.xml',names);self.assertIn('word/numbering.xml',names)
            doc=ET.fromstring(archive.read('word/document.xml'));ns={'w':document.W};text='\n'.join(n.text or '' for n in doc.findall('.//w:t',ns))
            self.assertIn(self.report['title'],text);self.assertIn(self.report['summary'],text);self.assertIn(self.report['assessment'],text);self.assertIn('3. Preserve the original number.',text)
            self.assertTrue(doc.findall('.//w:pStyle',ns));self.assertTrue(doc.findall('.//w:numPr',ns))
            for source in self.report['sources']:self.assertIn(source['url'],text)
            for name in names:
                if name.endswith('.rels'):self.assertNotIn('TargetMode="External"',archive.read(name).decode())
        try:from docx import Document
        except ImportError:return
        parsed=Document(io.BytesIO(raw));self.assertEqual(parsed.paragraphs[0].text,self.report['title']);self.assertEqual(parsed.paragraphs[0].style.name,'Heading1')

    def test_cli_backend_falls_back_without_officecli_and_never_overwrites(self):
        path=Path(self.tmp.name)/'导出 文件.docx'
        with patch.dict(os.environ,{'AGENT_OFFICECLI':''}):result=office.export_docx(self.report,path)
        self.assertEqual(result['adapter'],'builtin-docx');self.assertEqual(result['model_calls'],0);self.assertTrue(path.is_file())
        before=path.read_bytes()
        with self.assertRaises(ValueError):document.export_docx(self.report,path)
        self.assertEqual(path.read_bytes(),before)
        with self.assertRaises(ValueError):document.export_docx(self.report,path.with_suffix('.txt'))

    def test_text_budget_and_xml_control_characters(self):
        original=self.report['summary'];self.report['summary']='x'*240001
        with self.assertRaises(ValueError):document.docx_bytes(self.report)
        self.report['summary']=original+'\x00保留正文'
        with zipfile.ZipFile(io.BytesIO(document.docx_bytes(self.report))) as archive:
            root=ET.fromstring(archive.read('word/document.xml'));text=''.join(n.text or '' for n in root.iter('{'+document.W+'}t'))
        self.assertIn('保留正文',text);self.assertNotIn('\x00',text)

if __name__=='__main__':unittest.main()
