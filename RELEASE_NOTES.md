# v0.13.0 · 文件建库、确认后监测与私有技能学习

浏览器和 CLI 支持按项目建立私有知识库，保存原件、版本、出处与可重建索引；监测方案预览并确认后执行，区分检查与汇总周期，保留增量、失败和发送回执；学习默认关闭，可选择本地整理或限额模型提炼，查看并回退私有技能。保留原有报告、看板、产品路径与 Mac/Windows/Linux 支持。

Private collections, confirmed watches and opt-in procedural learning share the existing standard-library runtime. External delivery requires an operator-configured Hermes CLI destination and explicit confirmation; no jobs or recipients are enabled by installation. See [setup, recovery and limits](docs/continuous-research.md).

---

# v0.12.1 · 等待任务结束后清理测试工作空间

HTTP 任务创建验收先确认后台任务已完成并释放数据库，再清理临时工作空间，避免 Windows 的文件占用错误。保留 v0.12.0 的办公适配与六类任务能力。

The HTTP task regression waits for the actual worker to finish before removing its temporary workspace. The Office adapters and product task contracts introduced in v0.12.0 remain supported.

---

# v0.12.0 · 办公资料与按任务研究

可选本地 MarkItDown 适配器导入 DOCX/XLSX/PPTX；iOfficeAI/OfficeCLI 将完整已保存报告导出为可编辑 Word，不额外调用模型。六类产品任务契约接入网页、CLI、HTTP 与原有 MCP 运行接口，首次保存后恢复沿用原内容。

The base runtime remains standard-library only. Optional adapters are operator-configured local programs; no third-party prompt collection or team runtime is bundled. Research tasks can omit enterprise context. See [setup and limits](docs/office-and-tasks.md) and [integration decisions](docs/integration-references.md).

---

# v0.11.0 · 工具接入与可选研究深度

本地 MCP 服务默认只读；显式开放后，客户端可以在原有范围和预算内创建、恢复、暂停或取消任务。外部 MCP 搜索只接收允许的公开关键词；可选研究分支将不同问题的进度与结论随任务保存。文档技能增加输入输出说明与依赖提示，仍不执行脚本或增加权限。

See [MCP setup](docs/mcp.md) and [research depth](docs/research-depth.md). Base runtime remains standard-library only on Mac/Windows/Linux. Existing reports, country dashboards, product records and direct report saving remain supported. Public formulas and generic workflows stay open; specialized prompts, private knowledge and customer materials are not bundled. [Contact the author](https://github.com/workstonedai-collab) for further discussion.

---

# v0.10.0 · 业务关联与可追溯的选择

出海项目新增交易各方责任、单一币种报价情景测算、验证顺序及新资料对既有决策的影响。原有报告和项目记录继续保留，操作者选择不会被自动改写。

See [decision paths](docs/decision-paths.md) for examples and limits. Generic workflow and formulas remain public; specialized prompts and private knowledge are not bundled. Existing Mac/Windows/Linux support is retained.

---

# v0.9.0 · 研究记忆与问题相关的上下文

同一项目可以接续来源陈述、假设、判断与拟议方案，保留原来源与修改原因。操作者决定只能由操作者记录。浏览器、CLI 和 HTTP 支持查看、修订、版本历史及移出记忆；任务恢复沿用原快照。确定性的相关性选择兼顾支持/反对依据和关键约束，不增加独立模型审稿流程。

Existing reports, public dashboards, operator facts and Mac/Windows/Linux interfaces remain supported. Source statements are not certified facts; removal affects future memory recall, while saved runs and reports remain separate records. Public formulas and generic research steps remain available; specialized prompts, private knowledge and customer materials are not bundled. [Contact the author](https://github.com/workstonedai-collab) for further discussion.

---

# v0.8.0 · 可接续的研究工作表与受控取材

研究问题、原文摘录、支持或反对的依据、假设与下一步现在可随任务保存，支持恢复、浏览和导出。可选公开检索只组合操作者指定的词项，并持续计入查询预算；新增本地 CSV/TSV/TXT/Markdown 与可选 PDF 文本导入，保留行或页的位置。搜索摘要只能用于发现来源，不能作为正文引用。

Repeated source reads now restore the original saved excerpt in context, including material beyond page banners. A no-progress notice encourages a scoped delivery while existing step/time/call controls remain in force. Completed reports save directly without a separate reviewer or rewrite pass.

实际使用 MiniMax-M3.1-Flash 完成两组历史公开资料案例，各 9 次调用；另有一次受限 GOV.UK 自主检索先触发无进展保护，修复上下文复用后以同一任务剩余 1 次调用完成报告。后者仅取得一篇公告正文，报告明确保留原产地规则缺口；不作为完整法律意见或全网覆盖证明。原稿没有人工改写。模型配置与验收原始文件保留在仓库外。

Base runtime remains standard-library only on Windows/macOS/Linux. PDF extraction is optional, limited to text PDFs; it does not add OCR or guarantee complex table recovery. Older tasks, evidence IDs, public dashboards and report fields remain supported. Public formulas and generic research steps stay open; specialized prompts, private knowledge and customer materials are not bundled. [Contact the author](https://github.com/workstonedai-collab) for further discussion.

---

# v0.7.1 · 直接生成报告的真实案例验证

新增每个项目三组历史事件案例和显式运行工具，保留未经人工改写的模型动作、报告及回执。改进首次写作对日期节点、来源与题设、方案取舍和预算的处理；历史任务避免无效基线和空来源查询。实际运行结果及局限见报告质量文档。

Existing data, report fields, public dashboards and optional extensions remain supported. Cross-platform runtime stays standard-library only. Evaluation artifacts, credentials, private prompts and internal research materials remain outside the repository.

# v0.7.0 · Report writing, decision paths and source freshness

- Default frozen report-writing skill with versioned receipts; no extra rewrite call.
- Readable event assessment changes with source links and saved excerpts; project reports retain new alert snapshots.
- Optional entry-route tradeoffs, requirements, decision comparisons and validation priorities in saved projects and report exports.
- Registered-source success/failure/cache receipts and refresh status; task-specific tool advertising.
- Opt-in bounded live case evaluation and manual review checklist, retaining standard-library runtime and existing storage.

# v0.6.1 · Clearer language and readable project history

- Reworked Chinese project guidance, form labels and report-writing guidance while preserving sources, uncertainty and the open-source scope.
- Differentiated the two products’ starter questions and report focus.
- Project history now shows readable fields; original JSON remains available. Record-ID guidance follows the selected record type.
- Existing storage, commands and Windows/macOS/Linux support are unchanged.

# v0.6.0 · Product-specific private project workflows

在“项目持续跟踪”中整理企业画像，按需求、准入、渠道、交付、经济性与风险比较进入选项。保存方案依赖的经营假设和行动阶段；出现新的匹配资料时，定位需要重新研究的选项和阶段。

Reports save directly. Typed project updates use read source IDs and optimistic revisions; a concurrent operator edit retains the report without overwriting project state. Private business context is frozen per attempt history, while historical as_of reports exclude current business state and cannot mutate the live project. Existing evidence IDs and completed reports are preserved.

The private project desk keeps enterprise profiles, comparable entry options, business premises and roadmap progress. Newly saved matching public sources identify the assumptions, options and stages that need renewed research.

Use the [workflow guide](docs/product-workflow.md) for browser/CLI/PowerShell steps, constraints and the [attributed public replay](examples/public-project-case.json). The replay uses historical official-source summaries, fictional business conditions and a scripted substitute model; it is not a live-provider quality or current-advice evaluation. No external delivery or MCP is enabled.

Code MIT; data retains its own attribution. Public formulas and generic research steps remain open. Specialized prompts, private knowledge and customer materials are not bundled; [contact the author](https://github.com/workstonedai-collab) for further discussion.

---

# v0.5.0 · Project continuity and a bounded research kernel

本版完善两个产品共用的研究内核：同一项目可接续旧研究并管理私有资料，长资料分段读取，重复结果复用，文档技能按需加载。新增暂停/取消与显式恢复、模型请求用量记录及持续生效的调用上限。模型返回后重新计算时间，保留已经返回的有效报告并标出到期状态。

This alpha adds private project continuity, bounded context, shared tool contracts and document-only skills to the existing independently runnable packages. Additive private SQLite tables preserve previous tasks, evidence IDs and saved reports. Cross-platform tests exercise installed packages, synthetic substitute models and loopback HTTP; no paid model or external-search validation is implied.

See [the shared kernel guide](docs/kernel.md) for CLI/browser use, PowerShell examples, migration and data boundaries. Current task input takes precedence over project history. Private skills and source instructions remain operator-owned; scripts are not executed. MCP and new product-specific monitoring workflows are outside this batch.

Code MIT; public observations retain separate data terms. Public country formulas and general research steps remain available; specialized prompts and private knowledge are not bundled. Contact the author for further discussion.

---

# v0.4.1 · Native Windows support / Windows 原生适配

Windows 可直接使用 Python 安装与运行，无需 WSL 或 Docker。新增 PowerShell 安装、模型配置、保存恢复、导出与周期任务说明；现有 Mac 命令和默认工作空间保留。

本版修复默认编码、中文输出和跨平台发布检查路径，固定源文件 LF 换行；网页启动直接使用绑定地址，避免等待本机主机名反查。自动检查覆盖 Windows、macOS、Linux 的 Python 3.11–3.13，并单独验证 Windows 独立环境安装；使用虚构资料和本机 HTTP 验证国区查询、报告保存重开、导出、恢复与周期任务，不调用付费模型。桌面浏览器与外部模型服务需在使用环境中另行验证。

Native Windows setup uses the venv Python directly, without activation or execution-policy changes. UTF-8 data/output, Unicode workspaces, release integrity, persisted reports and loopback HTTP share the same runtime across all three systems. See [Windows setup](docs/windows.md) and repository Actions for execution results.

Code MIT; public country observations retain their separate attribution and terms. Country scoring formulas and general research steps remain public; specialized prompts and private knowledge are not distributed. Contact the author for further discussion.

---

# v0.4.0 · Public research runtime and country data

独立可运行的开源研究智能体，保留国区看板、世界银行公开分项、来源工具、任务恢复与报告保存导出。可通过显式本地说明文件配置自己的研究要求。

部分研究方法、专用提示词与相关知识内容暂未开源。如有需要或希望进一步交流，欢迎通过作者GitHub主页或项目Issue联系。国区评分配方、分项权重和通用研究步骤保留公开；专用提示词及私有知识不随包发布。

Self-hosted alpha with a CLI, browser workspace, attributed public observations, bounded research tools and optional operator-owned instructions. Code MIT; public data retains its separate attribution and terms.
