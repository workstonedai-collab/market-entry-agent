# 研究进展、公开检索与文档资料 / Research state and source ingestion

研究任务可以保存子问题、已保存资料摘录、假设、分析判断、拟议决策，以及下一步取材与停止原因。小问题仍可直接交付报告，不要求填满工作表，也不增加独立审稿或润色模型。

## 查看与恢复

浏览器任务详情中的“查看已保存的研究进展”可按需读取；已完成报告包含工作表快照，Markdown与JSON导出均保留。查询接口沿用本地服务的令牌、Host与Origin检查：`GET /api/research?run_id=任务编号`。

```bash
market-entry-agent --workspace ../private-research research-state RUN_ID
market-entry-agent --workspace ../private-research resume RUN_ID
```

工作表按任务隔离，不自动把旧报告当事实。更新有版本检查和重放记录，中断后不会重复增加相同研究修订。来源摘录必须逐字匹配已经成功读过的片段；若资料为导入摘要，引用的是该摘要而非官方文档原文。这验证出处与读取范围，不保证模型对片段的解释正确。`source_fact`、`hypothesis`、`judgment`和`decision_proposal`分别记录来源事实、假设、判断、建议；模型不能据此审批业务决策。

## 允许继续搜索的公开范围

原有`search_queries`固定查询保留。需要模型根据研究进展组合新查询时，在任务JSON中另设：

```json
"public_search": {
  "terms": ["Vietnam", "industrial pumps"],
  "facets": ["import requirements", "distributor after sales"],
  "max_queries": 6
}
```

也可在网页“允许智能体在公开范围内继续检索”里逐行填写。模型只能选择这两组公开词的索引组合查询，不能把企业背景、报价、私有记忆或查询理由直接发给搜索服务。公开词表须由任务发起人确认可以发送。每个任务最多12个不同组合，默认6个，预算跨恢复继续累计；失败查询也占用组合预算，避免反复失败后无限换词。搜索结果是线索，仍须获取并读取正文后引用。查询执行另受任务时间及模型调用预算限制。

搜索沿用显式配置的`AGENT_SEARCH_API_KEY`。没有配置`public_search`时，不展示自适应查询工具，不改变旧任务行为。历史任务仍排除未知或晚于截止时点的发布日期，不把当前搜索结果冒充当时信息。

## 导入本机文档

操作者明确选择文件，不向模型提供任意文件读取或命令执行。基础支持UTF-8的TXT、Markdown、CSV和TSV；表格保留列名、空单元格、数据行范围与货币等原始文本，不自动换算单位。单个文件最多8MB，表格最多一万行；宽度不一致的表格会返回明确错误。

创建来源元数据JSON，填写标题、来源URL、国区、主题和已知发布日期：

```json
{
  "title": "Fictional product quote",
  "url": "https://example.org/fictional-quote",
  "countries": ["Vietnam"],
  "topics": ["trade"],
  "published_at": "2024-01-01",
  "public": false
}
```

该URL只作为来源标识，本机导入不会访问它。不要把私有文件本机路径当作公开出处。`public`默认false，私有文档不能写入工作空间之外的共享证据库。共享库只适合操作者明确允许共享的公开/许可资料；导出文件由操作者自行管理。原文、页码或数据行范围、内容哈希和私有/公开标记会保留，磁盘文件路径不进入证据记录。

```bash
market-entry-agent --workspace ../private-research import-document ./quote.csv ./metadata.json
```

Windows命令使用虚拟环境Python即可：

```powershell
& ".\.venv\Scripts\python.exe" -m market_entry_agent --workspace ..\private-research import-document .\quote.csv .\metadata.json
```

## 可选PDF适配器

基础包仍仅依赖Python标准库。PDF可以使用系统已安装的Poppler `pdftotext`，或在单独的文档适配环境安装[pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)：

```bash
python -m venv ../pdf-adapter
../pdf-adapter/bin/python -m pip install pypdf
export AGENT_PDF_ADAPTER_PYTHON=../pdf-adapter/bin/python
market-entry-agent --workspace ../private-research import-document ./report.pdf ./metadata.json
```

Windows对应设置：

```powershell
python -m venv ..\pdf-adapter
& "..\pdf-adapter\Scripts\python.exe" -m pip install pypdf
$env:AGENT_PDF_ADAPTER_PYTHON = (Resolve-Path "..\pdf-adapter\Scripts\python.exe").Path
```

PDF解析在操作者配置的独立子进程中执行，有时间和文本大小上限，不执行PDF中的代码。当前读取前40页并保留页码及页内偏移；长文档请按需要拆分，不宣称全文覆盖。扫描图片需要另行OCR；布局抽取不能保证复杂PDF表格的单元格关系，精确计算优先导入原始CSV/TSV。没有适配器时返回明确说明，仍可导入有权限使用的已提取文本。

登记或搜索发现的公开PDF可沿用`fetch_page`获取，它会返回页面证据ID列表；仍需分别读取要引用的页面。网络访问继续受原域名与公网地址检查，解析使用任务剩余时间。

## 工具与直接写作

`research_state`读取当前工作表；`update_research`按`expected_revision`更新；`adaptive_search`只接受公开词索引。来源事实的`fragments`需要`evidence_id`、`offset`和`quote`，引用必须来自本轮已读资料。完整工具参数可用`tools`命令查看。

工作表帮助首次完整写作持续保留依据与问题，不是独立审稿门禁。没有新信息时可记录剩余缺口后直接交付条件判断；不要求反复搜索或循环修稿。专用研究提示词、私有方法和客户材料继续留在仓库外。

Research state is durable and revisioned, while raw evidence remains separate. Query composition is restricted to explicitly public operator terms, not arbitrary model prose. PDF parsing is optional and isolated; base installation remains standard-library only. Existing missions, reports and exports remain readable.
