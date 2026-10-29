# Office 文件与任务入口 / Office adapters and task modes

先把研究资料读进来，完成分析，再把已保存报告带到日常工作中。基础运行仍只依赖 Python 标准库；办公适配器在你明确选择后使用，不让模型执行命令，也不自动安装插件。

## 导入本地 Office 资料

在独立环境安装 `markitdown[docx,xlsx,pptx]==0.1.9`，把该环境的 Python 绝对路径填入 `AGENT_DOCUMENT_ADAPTER_PYTHON`。原有 `import-document FILE METADATA.json` 现在可读取 DOCX、XLSX、PPTX。元数据和私有/公开选择与[文档导入](research-state.md)相同，默认私有；私有文件不能写入共享证据库。

调用使用固定的隔离 Python 脚本、字节流输入和关闭插件的 MarkItDown，不配置 LLM、OCR 或云转换。最多读取 8 MB 文件，压缩容器展开预算 32 MB，转换时限 40 秒。输出保留转换后文本偏移与文件哈希；不把文本偏移冒充原文页码、单元格或幻灯片位置，不执行宏或重新计算公式。复杂排版及公式值仍需对照原件。

## 导出可编辑 Word 报告

从 v0.14.0 开始，基础安装已有内置 DOCX 导出，可在网页直接下载，或用原来的导出命令，不必额外配置 OfficeCLI。内置路径保留完整文字，设置标题和列表；不调用模型。下面的 OfficeCLI 配置仍适用于希望继续使用该可选程序的操作者，命令行在明确设置它后沿用原路径。[配置与日常使用](setup-and-use.md)

使用 [iOfficeAI/OfficeCLI](https://github.com/iOfficeAI/OfficeCLI) v1.0.158 的本机二进制，先核对其发行校验值。这里使用的是本地文档编辑工具；同名的其他服务需要单独评估。

macOS / Linux:

```bash
export AGENT_OFFICECLI=/absolute/path/to/officecli
export AGENT_DOCUMENT_ADAPTER_PYTHON=/absolute/path/to/document-venv/bin/python
market-entry-agent export RUN_ID --output ../private-output/report.docx
```

Windows PowerShell:

```powershell
$env:AGENT_OFFICECLI = 'C:\Tools\officecli.exe'
$env:AGENT_DOCUMENT_ADAPTER_PYTHON = 'C:\Tools\document-venv\Scripts\python.exe'
& '.\.venv\Scripts\python.exe' -m market_entry_agent export RUN_ID --output ..\private-output\report.docx
```

导出沿用已保存完整报告，包括来源和必要标记，不再调用模型、不改写旧报告。Word 中保留 Markdown 文字记号，方便继续编辑；当前不是排版模板，也没有承诺一键生成演示文稿或测算工作簿。已有输出文件不覆盖，失败不会更改已保存报告。导出文件可能包含私有材料，按本地客户资料管理。

适配器采用固定命令、参数数组、总时限、隔离临时文件和不含模型密钥的进程环境，关闭 OfficeCLI 自动驻留。配置的 Python 和 OfficeCLI 仍是你信任的本机程序，这些措施不等于操作系统沙箱。

## 按任务选择入口

网页“开始一项研究”可选择本次任务；命令行 `market-entry-agent task-modes` 列出本项目三种入口。运行时通过 `--task-mode MODE` 或任务 JSON 的 `task_mode` 指定。MCP 的 `run_create` 与 HTTP 创建任务也沿用这个字段；权限与预算不变。

地缘项目：`topic-research`（专题研究与问题解释）、`event-tracking`（事件跟踪与报道准备）、`interest-watch`（利益影响与风险观察）。研究与报道任务不要求企业背景，不编造采访、独立核实或业务利益。

出海项目：`market-options`（选市场与进入方式）、`transaction-review`（交易责任与业务测算）、`operating-watch`（经营前提与方案跟踪）。同一用户可按当前问题切换，仍由操作者记录真实报价、交易责任和最终选择。

任务契约有内容哈希，随首次系统上下文保存，恢复沿用原内容。它引导首次取材与写作，不增开子智能体、不增加审批或独立审稿。离线 demo 只验证任务、保存及接线，不作为六类任务的真实模型质量验收。

## Integration status

Office import uses an optional operator-owned MarkItDown environment; DOCX export invokes a pinned, separately installed iOfficeAI/OfficeCLI binary. The explicit OfficeCLI adapter remains a CLI option; browser report downloads use the built-in DOCX writer, and private library uploads reuse the optional import adapter. None is an arbitrary model-executed command. Product task selection is wired to browser, CLI, HTTP and the existing MCP run interface. Existing reports, source contracts and independent Mac/Windows/Linux workspaces remain supported.

See [integration references and boundaries](integration-references.md) for adoption decisions. Generic contracts and adapters are public; specialized instructions, private knowledge and customer files stay outside the repository.
