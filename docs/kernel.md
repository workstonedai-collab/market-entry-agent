# 项目记忆、上下文与执行 / Shared kernel guide

v0.5.0 adds explicit project memory, bounded context, document skills, tool contracts and run controls to the existing CLI/browser runtime. Both products remain independently installable and standard-library only. Research still forms a report directly and saves it with sources; there is no extra review/rewrite service.

## 先接续一个项目 / Continue a project

同一工作空间中，给同一家企业或研究项目使用稳定的 `project_id`，例如 `equipment-asean`。ID 为 1–64 个英文字母、数字、点、下划线或连字符。不同客户继续使用不同工作空间。项目 ID 用于关联任务，不会自动把不同企业归为一类。

```bash
market-entry-agent memory-set equipment-asean product "虚构演示：设备出口"
market-entry-agent memory-set equipment-asean budget "虚构演示：预算待确认"
market-entry-agent memory equipment-asean
market-entry-agent demo --project equipment-asean
market-entry-agent run examples/project-mission.json --engine demo --project equipment-asean
```

网页中可填写“项目 ID”，在“管理本项目的私有资料”中保存、查看和移除资料。改变项目 ID 会切换资料范围。本次任务输入优先于旧资料；操作者录入和历史分析均不会自动升级为独立来源证据。模型仍须在本次运行读取可以引用的证据。

CLI prefixes can be replaced with `python -m market_entry_agent`. On Windows PowerShell, use the venv Python directly:

```powershell
& ".\.venv\Scripts\python.exe" -m market_entry_agent memory-set equipment-asean product "虚构演示：设备出口"
& ".\.venv\Scripts\python.exe" -m market_entry_agent demo --project equipment-asean
& ".\.venv\Scripts\python.exe" -m market_entry_agent run .\examples\project-mission.json --engine demo --project equipment-asean
```

Project memory stays in the private tasks database, scoped to this product and explicit project ID. Sharing a public evidence database does not share project facts, reports or instructions. Without a project ID, recall retains the legacy same-mission behavior with punctuation/spacing normalization of the question. Related but differently worded research requires an explicit project ID.

## 更正、时效与遗忘 / Correct, expire and remove facts

```bash
market-entry-agent memory-set equipment-asean budget "虚构演示：以本次新预算为准"
market-entry-agent memory-set equipment-asean temporary-note "虚构短期安排" --expires-at 2027-01-01T00:00:00Z
market-entry-agent memory-forget equipment-asean temporary-note
```

相同键的新值会替代旧值，保留版本关系；重复保存相同值不新增版本。每项目最多 40 个有效资料键，每值最多 4,000 字符。过期资料不进入当前召回；历史 `as_of` 会排除截止时间之后记录的资料和生成的报告。无时区时间按 UTC 处理，建议显式使用 `Z`。

任务开始时固定一份相关项目资料、历史分析与技能快照；失败恢复继续使用原快照，避免中途改变研究条件。已完成报告不因后来更正资料而改写。要使用更新后的资料或技能，请新建研究。

`memory-forget` removes all revisions of that key from the project-fact store. Previously saved task snapshots, reports and backups are separate records and are retained. It is not a forensic erasure command. Operator facts are not automatically sent to public search; configured model mode receives the selected private task context. Recall inspects up to 100 recent project reports and returns at most five summaries. Bounded context initially shows a small selection; the `recall` and `read_result` tools can inspect the frozen material further.

## 上下文与资料分段 / Bounded context and source excerpts

任务可配置：

```json
{
  "question": "围绕本项目的问题继续研究",
  "countries": ["越南"],
  "topics": ["trade"],
  "project_id": "equipment-asean",
  "skill_ids": ["evidence-brief"],
  "context_budget_chars": 48000,
  "max_model_calls": 24,
  "max_steps": 12,
  "deadline_seconds": 180
}
```

`context_budget_chars` is a character budget, not a token estimate: default 48,000, configurable from 16,000 to 160,000. The host retains fixed instructions/current input, selected frozen project context, loaded skills, progress and recent source excerpts. Full observations stay in local SQLite steps. Older bulky outputs are replaced in the model context by compact previews and step references, without an additional summarization model.

`read_evidence` accepts `offset` and `limit` (1–6,000 characters) and returns source ID, dates, total length and whether the excerpt is truncated. `read_result` reads a bounded excerpt of a saved step from this run. Source citations still require `read_evidence`; reading a result reference alone does not authorize a citation. The persisted evidence ID/content is preserved, including pre-upgrade imports. Chinese/English economy aliases are matched at lookup time rather than rewriting old IDs. Nonempty keyword searches report actual matches; an empty query explicitly browses in-scope evidence.

重复的、输入未变的只读结果会复用原检查点，记录 `reused_step`；更换资料片段的 offset 仍可读取更多内容。连续四个错误或无新增结果的复用会结束本轮，保留已完成步骤供显式恢复。固定输入本身超过预算时会在调用模型前报错；请精简输入或在新任务中提高预算，系统不静默截掉任务要求。

## 文档技能 / Document-only skills

```bash
market-entry-agent skills
market-entry-agent tools
market-entry-agent run examples/project-mission.json --engine model --project equipment-asean --skill evidence-brief
```

Two generic built-ins are supplied: `evidence-brief` and `country-comparison`. The model initially sees a catalog and can call `load_skill`; the user can explicitly select a skill in the browser or mission. At most three skill documents may be active in one run. Loaded versions are recorded by content hash.

Optional private skills are loaded only from an explicitly exported `AGENT_SKILLS_DIR`, outside the repository. Set it in the same shell that starts the app (`$env:AGENT_SKILLS_DIR` in PowerShell). Layout:

```text
private-skills/
  your-research-outline/
    SKILL.md
```

```markdown
---
name: your-research-outline
description: Explain when this private research outline should be used
---
Your operator-owned research instructions.
```

这是最小文档加载器：只支持一行式 `name` 与 `description` 前置信息，不宣称完整实现所有 YAML/Agent Skills 扩展。可配置最多 8 个私有技能，每份最多 8,000 UTF-8 字节，不允许越出目录或覆盖内置同名技能。本批只加载 `SKILL.md`，不执行 scripts，不跟随附录，不扩大工具权限。技能正文会发送至所配置模型，并保存在该任务的私有快照中；普通网页响应与执行记录只展示技能名称和版本。改动文件只影响新任务。

General public templates ship with the package. Specialized methods, prompts and private knowledge need not be published. Keep private skill directories, instructions and runtime databases outside Git source. The original `AGENT_INSTRUCTIONS_FILE` remains supported and is also pinned on first attempt.

## 暂停、取消与恢复 / Run controls and recovery

```bash
market-entry-agent list
market-entry-agent pause-run RUN_ID
market-entry-agent resume RUN_ID
market-entry-agent cancel RUN_ID
market-entry-agent show RUN_ID
```

`pause-run` controls a research run; the existing `pause SCHEDULE_ID` still pauses a recurring schedule. A cancelled run is terminal; create a new task to continue. A paused or failed run can resume within its original step/model-call limits. Completed runs return the same saved result. Browser controls expose pause, cancel and resume.

Controls take effect at safe boundaries. An in-flight provider request may settle before the worker notices pause/cancel; the app does not claim that a cancellation instantly stops provider billing. No new tool starts after the control is observed. Owner fencing prevents an expired worker from overwriting a newer owner's checkpoints or results.

`deadline_seconds` remains a per-attempt wall-clock budget. Remaining time is recomputed after model calls and before tools. Once exhausted, the host does not start a new retrieval. A valid final report already returned is saved and labeled `finish_returned_after_attempt_deadline`, preserving useful output. A deadline after a nonfinal tool leaves the saved result available for resume.

`max_model_calls` limits attempts across explicit resumes, including failed requests: default twice `max_steps`, optionally 1–100. There are no automatic paid provider retry loops. Step limits remain 4–30. Repeatedly resuming a task cannot silently reset its model-call budget.

## 用量与运行记录 / Usage receipts

```bash
market-entry-agent usage RUN_ID
```

每次模型请求记录上下文字符数、用时、结果类别及技能版本。服务提供 token 用量时保存允许的计数字段；未提供就标明不完整，金额仍未知。替身测试计数不代表真实模型效果或账单。旧任务没有这些记录时会显示 tracking unavailable，不把缺失当作零消耗。旧版中断任务升级后恢复时，只统计升级后实际记录的调用，并标出 legacy_history_unmetered；无法补算旧请求或旧费用。报告 JSON 包含运行汇总，原报告与来源仍可导出。

模型内部推理、供应商响应正文和凭据不作为运行记录保存。浏览器仅显示简要请求次数、用时与服务已报告的 token 信息。

## 检查与升级 / Verify and upgrade

```bash
python -m unittest discover -s tests -v
python scripts/verify_kernel.py
python scripts/verify_portability.py
python scripts/check_public_release.py
python scripts/check_core.py
```

PowerShell uses the same arguments after `& ".\.venv\Scripts\python.exe"`. CI runs these against installed packages on Windows, macOS and Linux with Python 3.11–3.13, plus a clean Windows installation and container demonstration.

`verify_kernel.py` uses synthetic material and a scripted substitute model to verify project recall, aliases, source paging, context bounds, duplicate reuse, skill versions and saved-result recovery. `verify_portability.py` exercises real CLI/loopback HTTP, including project facts and controls. Neither calls a paid model or external search. Actual research quality and monetary savings require separate provider-backed evaluation.

升级前先停止自己的 server/worker，并备份整个私有工作空间。v0.5.0 首次打开时仅增加私有运行表及显式项目关联，不改写旧证据 ID、任务正文或已保存报告；旧任务的成功 finish 检查点可直接恢复成报告，无需再次调用模型。请使用同一工作空间路径。现有 Mac/Linux 命令、Windows 原生安装方式和世界银行公开国区数据保持支持。

HTTP additions use the existing workspace token and Host/Origin checks: `GET /api/skills`, `GET /api/memory?project_id=...`, `POST /api/memory` (set/forget) and `POST /api/control` (id/state). These are local product APIs; MCP and new external connectors are outside this batch.
