# 项目持续跟踪 / Product workflow guide

把企业情况、候选市场、进入方案和推进计划放在同一个项目里，后续研究可以接着已有判断往下做。v0.6.0 起支持这条使用路径。项目记录、历史版本、提醒、画像和计划只保存在私有任务库；公共证据库仍只承载显式导入或取得的公开资料。项目由你自行部署，面向单人使用，不自动向外发送消息。

## 从网页开始

1. 按原安装说明启动服务，打开“项目持续跟踪”，输入稳定的项目 ID，再点“打开项目”。不同客户使用不同工作空间。
2. 选择要新增的记录，填写表单并保存。后续从记录卡片的“查看与修改”更新；保存时会检查版本，发生冲突后先重新打开记录。“修改记录”按字段展示各版内容，也可展开查看原始 JSON。
3. 用“继续研究这个项目”带入项目 ID 和技能。该按钮带入项目国区、主题并清空上一项任务背景与公开查询；确认问题并补充本次要求及允许发送的公开关键词。模型模式会接收所选项目的私有资料，公开搜索仍只接收明确的公共查询。
4. 研究直接保存。智能体提出的项目更新经格式、引用和版本检查后，与报告一起保存。如果你在研究期间修改了同一条记录，报告仍会保留，建议更新会暂存为“待对照”，由你决定如何处理。
5. “对比本地资料”只检查本地已保存资料，不刷新来源。真实新资料需通过原有取证工具、导入、来源刷新或研究取得。项目页展示本地提醒，原研究提醒收件箱继续保留。

表单中的记录编号用于关联事件、选项、假设和阶段。使用字母、数字、点、下划线或连字符，最多64字符。源码中不包含客户专用配置；界面导出的私有项目文件应留在仓库之外。

## 命令行与 PowerShell

```bash
market-entry-agent project equipment-asean
market-entry-agent project-save equipment-asean my-command.json
market-entry-agent project-history equipment-asean KIND RECORD_ID
market-entry-agent project-check equipment-asean
market-entry-agent run examples/project-mission.json --engine model --project equipment-asean --skill project-continuity
```

`my-command.json` 为 UTF-8 JSON：

```json
{
  "kind": "KIND",
  "id": "stable-record-id",
  "expected_revision": 0,
  "data": {}
}
```

新增记录使用版本0。更新已有记录时填当前 `revision`，提交该条记录的完整新内容；内容相同的重复写入保持原版本。每个项目每种业务记录最多100个，运行收据、游标和提醒各最多5,000个；版本历史接口每次返回最近100个版本，不删除旧报告。适合范围明确、记录量有限的研究项目，达到容量上限时应归档工作空间并另建项目。

Windows 不需激活环境或改变执行策略：

```powershell
& ".\.venv\Scripts\python.exe" -m market_entry_agent project equipment-asean
& ".\.venv\Scripts\python.exe" -m market_entry_agent project-save equipment-asean .\my-command.json
& ".\.venv\Scripts\python.exe" -m market_entry_agent project-check equipment-asean
```

## 智能体如何使用项目

`project_state` 返回本次任务开始时保存的项目目录与更新规则；传入 `kind` 和 `id` 可读取某一条完整记录，较长结果可用 `read_result` 分段查看。失败恢复继续使用原快照；本次用户输入优先。当前私有业务状态不进入 `as_of` 历史任务，历史报告不能修改当前业务项目。

模型可在 `finish.report.project_update.commands` 中提交允许更新的记录。来源必须在本任务读取并列在报告引用中，记录还检查国区、主题、关联对象和版本。它不能修改用户画像、暴露、反馈或决策，也不能替用户确认假设、选择方案或声明工作完成。结构和引用检查不等于独立事实审查。

项目摘要不会自动变成公共事实。企业提供的情况、公开资料、研究分析、建议计划和实际进度会标明各自来源。人工录入或模型建议不等于已经过独立核实。

报告表达：报告从企业当前要做的选择讲起，结合产品、买方和经营约束比较方案，再说明取舍、需要验证的前提和下一步工作。国区背景用于支持分析，不能代替对具体业务的判断。用具体、自然的语言保留来源、日期和必要限制，避免空泛口号与重复提示。写作要求直接用于报告生成，不增加独立改写或审稿步骤。实际表述仍取决于所配置模型。

## 可复现的公开历史案例

```bash
python scripts/verify_public_case.py
python scripts/verify_public_case.py --workspace ../market-entry-agent-historical-case-workspace
```

指定的目录必须为空；该脚本不会往正在使用的客户工作空间写入案例。脚本使用本项目实际安装的代码、真实公开资料的自写摘要、虚构业务条件和替身模型动作，验证完整保存、重开、项目更新和去重路径。无需密钥，也不调用付费模型。它验证流程，不代表真实模型自行调查的质量、预测准确率或实际企业结果。

原始公开来源及日期保存在 [案例文件](../examples/public-project-case.json)。摘要不是对原网站正文或图像的整份复制；正文、地图与第三方数据版权仍归原权利人。当前取回的历史公告不能证明系统当时已获取信息。案例按资料发布顺序回放，不作为当前预警或当前产品合规结论。

可选 `--live` 会重新请求案例中列出的原始来源，记录 HTTP 状态、文件大小和原始响应 SHA-256。这个检查仅证明取得响应，内容语义仍需对照来源；不可用来源会逐项记入凭证，`live_sources_complete=false` 时不声称全部取得。CI 使用固定公开摘要，不访问外部来源。可用 `--output receipt.json` 保存回放凭证。

## 接口、升级与验证

新增本地接口沿用既有令牌、Host 和 Origin 检查：`GET /api/project?project_id=...`、`GET /api/project/history?project_id=...&kind=...&id=...`、`POST /api/project`（project_id与command）、`POST /api/project/check`（project_id）。它们不是 MCP，也不是商业多租户接口。

升级前停止自己的 server/worker，备份完整私有工作空间，再安装新包。首次打开只增加 `business_records` 表；不改写旧任务、证据编号和已完成报告。既有 worker 继续按原任务执行；新项目任务完成时，会检查保存的业务资料并记录结果。只有启动 worker 才有周期运行，GitHub 发布不等于全天候托管。

```bash
python -m unittest discover -s tests -v
python scripts/verify_kernel.py
python scripts/verify_portability.py
python scripts/verify_public_case.py
python scripts/check_public_release.py
python scripts/check_core.py
```

All existing CLI/browser/report/country functions remain available. The packages remain standard-library only and independently installable on Windows, macOS and Linux. CI runs Python 3.11–3.13, clean Windows PowerShell installation and a container demonstration. Private state is additive; original saved reports and evidence IDs are preserved. MCP, external delivery, provider-backed quality evaluation and unrestricted semantic event clustering are not included in this batch.

## 企业画像、进入选项、假设与进度

先以 `profile/main` 保存企业画像：具体产品和用途、买方、阶段、国区、能力、约束及预算。阶段可选寻找方向、已有目标市场或已进入经营；未知预算可留空。目前通过表单录入和修改企业情况。文字材料也可以放入研究任务，由模型结合项目资料分析；尚不支持从任意文件自动生成企业画像。

进入选项同时包含国区、进入方式、采用或暂缓理由，以及需求、准入、渠道、交付、经济性、风险六项内容。每项可以是来源事实、条件性分析或明确缺口，不自动补齐数值。用户可选择、暂缓或标为受阻；模型只能提出候选方案。宏观指数作为背景，不直接生成企业适配排名。画像改变后，旧选项会提示“企业条件已更新”，原研究与原选择理由继续保留。

经营假设记录方案依赖的前提，关联选项和行动阶段，并指定需监测的国区与主题。保存时以当前已保存的匹配资料为基线；随后出现新的、有发布日期的非演示资料，检查器形成提醒，将假设标为 needs_review。它只表示有新资料待研究，不自动判定假设已被证伪或规则已适用于该企业。无关、未来日期和无发布日期的资料不触发该检查。研究或用户重新判断并保存后，已知资料成为新基线，避免对同一信息反复提醒。已有提醒作为历史保留。

行动阶段保留目标、工作、交付物、完成信号、关联选项和前置阶段。模型只能创建或更新仍处于建议计划状态的阶段；用户更新进行中、受阻或已完成。标记完成时需写实际结果说明，并要求前置阶段已完成。依赖不得成环。阶段完成是用户的进度声明，不是系统证明项目已经落地。

决策记录用于保存采用或暂缓方案的理由及关联选项，模型不能替用户提交决策。研究报告直接保存，项目更新有版本；不会因后续画像、假设或进度改变而改写原报告。

```mermaid
flowchart LR
  P[私有企业画像] --> R[围绕当前决策取证]
  R --> O[进入选项比较与建议计划]
  O --> A[经营假设与观察范围]
  O --> T[行动阶段与用户进度]
  N[新增已保存的匹配公开资料] --> A
  A --> U[定位受影响选项和阶段]
  U --> R
```

本项目案例回放欧盟理事会2025-06-18关于 CBAM 简化的临时协议公告与2025-09-29通过公告。虚构企业的两个进入选项及一个验证阶段依赖原政策阶段假设；新公告进入后形成定向提醒，计划仍是建议计划状态。例子不计算税费，也不认定虚构产品、进口商或货量已获豁免；正式生效及具体适用范围须另查原始法律文件。

Enterprise conditions, source facts, analysis and progress declarations remain distinct. Options use comparable dimensions without an automatic country-index ranking. New matching public evidence flags a premise for research and links affected options/stages. It does not silently rewrite a report, select a channel, assert legal applicability or mark work complete. The public historical replay uses fictional enterprise conditions and a scripted substitute model.
