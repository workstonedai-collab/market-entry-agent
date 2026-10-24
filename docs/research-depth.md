# 按问题展开的研究分支 / Optional research depth

当一个选择取决于几个不同前提时，可以分别检索，再汇入同一份报告。例如，出海方案可以分别看规则适用与交易成本；风险任务可以分别看事件进展与业务暴露。小任务无需开启分支。

```json
{"question":"A decision that needs more than one source path","countries":["Vietnam"],"topics":["trade"],"public_search":{"terms":["Vietnam","industrial pumps"],"facets":["import requirements","rules of origin"],"max_queries":4},"research_depth":{"max_branches":2,"max_queries_per_branch":2},"max_steps":18,"max_model_calls":20,"deadline_seconds":600}
```

在浏览器填写公开词范围后，可勾选“分别研究会改变选择的几个问题”。默认最多 2 个分支，每个最多 2 个不同检索。任务 JSON 可设置最多 4 个分支、每个最多 3 个检索；全任务公开查询上限仍最多 12 条，恢复后继续累计。时间、动作与模型调用上限继续使用原任务设置。

`research_branch` saves a stable question ID and performs an indexed public-term search; the branch question and private reason are retained locally, never added to the query. The agent then uses the existing fetch/read tools. `close_branch` saves a conditional conclusion, read original evidence IDs and a stopping reason. Branch questions do not change under the same ID, and closed conclusions are retained. A new task is used for reassessment.

These are sequential research paths inside one agent loop. There are no nested model workers, recursion or separate hidden budgets. Completed search results are reused after interruption; failed attempts and missing sources stay visible. A branch can stop when material is sufficient, public sources are exhausted or budgets approach their limit. A final report may retain visibly unfinished branches; closure is not a new review gate.

## 查看与恢复

- `research-state RUN_ID` and `GET /api/research?run_id=...` include saved branches.
- The task detail's saved-research button reads progress on demand, with no new polling loop.
- Saved JSON/Markdown and browser exports retain branch questions, conclusions, state and stopping reasons.
- MCP `research_read` uses the same saved state; existing pause/cancel/resume controls remain available.

## 文档技能的输入输出说明

Operator-owned `AGENT_SKILLS_DIR` skills can optionally add one-line metadata to their existing frontmatter:

```yaml
---
name: route-comparison
description: Compare permitted routes with explicit assumptions
inputs: Current mission, transaction conditions and read evidence
outputs: Conditional option comparison and next checks
requires_tools: project_state, read_evidence
---
Use the current mission and permitted source scope. Preserve unknown prices.
```

The catalog exposes this contract and a content hash. `load_skill` reports unavailable tool dependencies without enabling them or executing scripts. Old name/description-only skills continue to load. Contracts document expectations; they do not impose independent model grading, automatic rewriting or additional approvals. Private skills, prompts and knowledge remain outside public packages.
