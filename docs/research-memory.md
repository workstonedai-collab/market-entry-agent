# 研究记忆与上下文 / Research memory and context

同一项目下一次提问，可以接续之前保存的研究笔记。来源陈述、假设、判断、拟议方案与操作者决定分开保留；旧结论不会自动变成新的来源，也不会替操作者批准方案。

Completed current-time project runs capture their research notes into a private typed memory. The original run ID, exact saved fragment, source URL, publication date, reasoning type and change reason remain attached. Historical `as_of` runs do not write to live memory. Existing operator facts, previous summaries, country dashboards and reports remain supported.

## 使用

浏览器填写同一项目 ID，在“管理本项目的私有资料 → 研究记忆”查看、修订、读版本或移出后续记忆。模型只能形成拟议笔记，不能写“操作者决定”。操作者可在表单记录自己的决定；要修订同一记录，使用列表中的 ID 与当前版本。移除会清除该研究记忆的所有版本，避免旧笔记再次自动加入。

```sh
market-entry-agent --workspace ./private-work memory-notes equipment-asean
market-entry-agent --workspace ./private-work memory-note-save equipment-asean note.json
market-entry-agent --workspace ./private-work memory-note-history equipment-asean route-premise
market-entry-agent --workspace ./private-work memory-note-forget equipment-asean route-premise
```

Windows PowerShell uses the same arguments with `.\.venv\Scripts\market-entry-agent.exe`, or `.\.venv\Scripts\python.exe -m market_entry_agent`. No shell-specific processing or extra runtime dependency is needed.

`note.json`:

```json
{
  "key": "route-premise",
  "expected_revision": 0,
  "data": {
    "kind": "hypothesis",
    "text": "Fictional test: the proposed route needs a comparable freight quotation.",
    "change_reason": "Initial premise; no quote has been received.",
    "countries": ["Vietnam"],
    "topics": ["trade"]
  }
}
```

Operator editable kinds: `hypothesis`, `judgment`, `decision_proposal`, `operator_decision`. `source_fact` is captured from a run's exact read fragment and retains its original provenance. This label means a source statement was recorded; it does not certify independent truth. For an interpretation correction use a separate judgment, or remove the old record. Each change requires a reason and current revision. Stale edits fail without overwriting the newer record.

## 如何进入下一次任务

- 仅在显式相同项目 ID、同一产品和工作空间内调用；国区与主题限制继续生效。不同客户使用独立工作空间。
- 冻结首次运行时的记忆。恢复中断任务不会悄悄换成后来的修改；新任务读取最新版本。本次输入始终优先。
- 根据当前问题选择相关笔记，兼顾相关的支持与反对依据。确定性的词项匹配使用中文双字词与英文词，不调用向量服务；不等于语义检索或事实核实。最多带入 8 条研究笔记、12 条操作资料和 3 份旧摘要。
- 预算、交期、产品与约束资料优先保留。未选入的资料仍保留在本地，可经 `memory` 或 `recall` 获取；研究工作表可经 `research_state` 读取完整内容。
- 历史记忆带有来源指针，但不计为本轮已读。报告引用仍须实际读取原资料，搜索摘要仍不能充当正文。

## HTTP

Use the same workspace token and Host/Origin restrictions as the other local APIs:

- `GET /api/memory/notes?project_id=...&as_of=...` reads typed records.
- `GET /api/memory/notes/history?project_id=...&key=...` reads revisions.
- `POST /api/memory/notes` accepts `project_id`, `key`, `expected_revision`, `data`; `operation: forget` removes all memory revisions for that key.

This only manages private local state. Private context may be sent to the configured model under the existing mission behavior; memory text is never added to public search queries.

## 删除范围与限制

移出记忆只影响后续研究记忆召回。已保存报告、证据库、工作表、任务检查点与首次冻结的上下文是其他记录，仍然保留；不能把“移出记忆”理解为清空全部历史。需要删除客户全部资料时，停止工作进程后移除该客户的独立工作空间，并按自己的备份策略处理副本。

At most 500 typed memory keys are retained per project. Memory capture failure never discards an already generated valid report; `memory_result` records whether notes were captured. Original public data and private business records remain in their respective stores.
