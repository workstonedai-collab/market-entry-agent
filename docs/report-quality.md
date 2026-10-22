# 报告表达与案例验证 / Report writing and evaluation

报告默认应用 `report-writing` 文档技能，在首次生成中处理空泛铺垫、重复限制、生硬直译和内部过程词，保留数字、来源、日期、条件与分析深度。这些通用要求参考 [Humanizer-zh](https://github.com/op7418/Humanizer-zh)，没有把内部研究方法或专用提示词放入开源包。它不提供“AI 检测分数”，也不增加独立润色或审稿调用。

技能内容和版本在新任务开始时保存，实际进入模型上下文；报告的 `writing_skill` 和运行回执中的 `skill_versions` 可核对版本。失败后恢复沿用原任务的写作要求，已有报告正文保留原样。更改技能后从新任务开始使用。

风险报告先说明事件变化、关联业务和下一次观察条件；出海报告先回答企业当前要做的选择，解释方案取舍和验证顺序。必要限制放在相关判断处，避免每段重复；资料不足时仍可作有依据的条件分析。

## 查看已有报告

下面的命令只读取报告，不调用模型。输出目录必须为空并位于仓库之外。

```bash
python scripts/evaluate_reports.py --report ../private-report.json --output ../private-report-review
```

## 用真实模型跑公开历史案例

先按 [模型配置](live-research.md) 设置你选择的服务。示例资料来自 `examples/public-project-case.json`：公开来源摘要配合虚构经营条件。该命令会调用所配置模型，最多12次调用、10个动作、600秒；不搜索新网页，不发送客户文件。实际模型服务可能另有计费和限额。

```bash
python scripts/evaluate_reports.py --live --output ../private-live-evaluation
```

本次真实报告测试使用 MiniMax-M3.1-Flash、`reasoning_effort=low` 和6000输出 token 上限。选择同一服务时，可额外设置以下参数；密钥仍通过原环境变量提供，不写入报告或仓库。这是已测试的配置示例，其他服务按其支持范围设置。[MiniMax 官方接口说明](https://platform.minimax.io/docs/api-reference/text-openai-api)

```bash
export AGENT_MODEL_REASONING_EFFORT=low
export AGENT_MODEL_MAX_TOKENS=6000
```

Windows 可以直接使用虚拟环境 Python：

```powershell
& ".\.venv\Scripts\python.exe" scripts/evaluate_reports.py --live --output ..\private-live-evaluation
```

输出包含报告、来源、私有任务工作空间和结构检查清单。模型连接失败时保留任务进度，可用原命令行恢复同一任务，避免重新取证。检查引用是否列在来源表中，只能发现结构问题；仍需逐项阅读，判断来源是否支持结论、是否误用日期、建议能否执行，以及是否存在空话或不必要的重复。一次案例对照不能证明普遍质量或预测准确率。

## 方案取舍与验证顺序

出海报告可选 `decision_options`（name、fit、tradeoff、requirements、next_check、evidence_ids）与 `validation_priorities`（question、why_first、next_step、if_supported、if_not、evidence_ids）。需要固定结构时，在任务的 `output_sections` 填这两个名称。它们补充完整分析，不用表格替代推理；报价和成本未知时明确保留未知。

这两项会在网页和 Markdown / JSON 导出中保留。项目中的进入方案也可记录 `tradeoff`、`requirements` 和 `next_validation`，原有六项比较和选择状态继续有效。新增字段可不填写，旧记录仍可读取。

## 事件变化与来源更新

风险项目的提醒展示上次与本次判断，以及严重程度、状态、信息依据、业务影响或后续观察的具体变化。来源链接和已保存资料摘录可展开查看；摘录可能是导入摘要，不能把它称作已核实的原文。相关项目报告也保留本次生成的变化记录。

来源更新情况列出最近尝试、最近成功获取、最近失败和是否使用缓存。`refresh_hours` 可设1–720小时，默认24小时，只是用户设置的检查间隔。缓存命中不推进网络成功时间；失败保留上一次成功时间，错误正文和凭据不进入回执。历史资料的发布日期与抓取时间分开理解。

`GET /api/source-health` 沿用本地服务的令牌、Host 和 Origin 检查。统计范围只包含已登记来源，不保证全网覆盖，也不把获取成功当作事实已核实。来源监测回执保存在证据库的新增表中，不修改旧证据和报告。

新任务只向模型展示具备前提的工具：没有公开查询就不展示搜索，没有相应已登记来源就不展示来源刷新，没有项目编号就不展示项目读取。工具执行时仍检查范围与权限。

Report-writing instructions are frozen per run and applied during initial drafting. Live evaluation is opt-in and uses historical public summaries with fictional business conditions. Saved reports and additive decision fields remain compatible; no external delivery, mandatory rewrite loop or automatic writing-quality score is introduced.
