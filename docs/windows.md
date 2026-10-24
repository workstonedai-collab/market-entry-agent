# Windows 安装与使用 / Windows setup and use

本项目可以直接使用 Windows 上的 Python 运行，网页在本机浏览器中打开。无需 WSL、Docker 或管理员权限。当前自动检查覆盖 Windows runner 上的 Python 3.11、3.12 和 3.13；macOS、Linux 使用同一份代码并持续回归。

This project runs with native Windows Python and your local browser. WSL and Docker are optional. CI checks Python 3.11/3.12/3.13 on Windows, macOS and Linux, including CLI, HTTP, Unicode paths, persisted reports and explicit recovery. A separate Windows job follows the PowerShell venv installation below. These checks do not certify every desktop/browser or external model service.

## 1. 准备 Python 和 Git / Prerequisites

安装 [Python for Windows](https://www.python.org/downloads/windows/) 和 [Git for Windows](https://git-scm.com/downloads/win)。下例使用 Python 3.11；已安装 3.12 或 3.13 时，可将 `py -3.11` 替换成相应版本。也可以在 GitHub 下载源码 ZIP，解压后进入项目目录。

Install Python 3.11–3.13 and Git, or download and extract the source ZIP. Open PowerShell and check your interpreter. Commands below use Python 3.11; substitute your installed supported version if needed.

```powershell
py -3.11 --version
git --version
```

## 2. 安装到独立环境 / Install in an isolated environment

```powershell
git clone https://github.com/workstonedai-collab/market-entry-agent.git
Set-Location .\market-entry-agent
py -3.11 -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install .
```

之后的命令直接调用这个环境中的 Python，不需要运行 `Activate.ps1`，也不需要修改 PowerShell 执行策略。项目路径含空格时，先用 `Set-Location "你的项目目录"` 进入该目录。

Use the venv's Python directly. Activation and execution-policy changes are unnecessary. When a path contains spaces, quote it and use PowerShell's `&` call operator for the executable.

如果使用发行页的 wheel，可在建立环境后将安装命令替换为以下形式：

```powershell
& ".\.venv\Scripts\python.exe" -m pip install ".\market_entry_agent-0.6.0-py3-none-any.whl"
```

Download the matching wheel from this repository's [v0.6.0 release](https://github.com/workstonedai-collab/market-entry-agent/releases/tag/v0.6.0); it uses the same runtime as the source installation. Source-based checks below require the source checkout.

## 3. 无需密钥，先跑演示 / Run the no-key demonstration

```powershell
$workspace = Join-Path $env:LOCALAPPDATA "FieldAgents\market-entry-agent"
& ".\.venv\Scripts\python.exe" -m market_entry_agent --workspace "$workspace" demo
& ".\.venv\Scripts\python.exe" -m market_entry_agent --workspace "$workspace" country "越南"
& ".\.venv\Scripts\python.exe" -m market_entry_agent --workspace "$workspace" serve
```

浏览器打开 **http://127.0.0.1:8712**。查看已保存演示、国区看板和多国比较，再尝试报告导出。`demo` 使用虚构资料与规则，不调用模型；国区快照来自带来源说明的公开统计。服务在当前窗口运行，按 `Ctrl+C` 停止。关闭后用同一工作空间启动即可回看结果。

Open the local URL, inspect the synthetic demonstration and country desk, and export a saved report. `serve` stays in the current terminal; stop it with `Ctrl+C`. The same workspace retains your reports across restarts. The default workspace, when omitted, remains `~/.field-agents/market-entry-agent` on every OS; the explicit example above uses Windows LocalAppData. Keep one consistent location.

## 4. 接入模型与公开搜索 / Configure a model and public search

在启动程序的同一个 PowerShell 窗口设置你选择的服务：

```powershell
$env:AGENT_MODEL_BASE_URL = "https://your-compatible-provider.example/v1"
$env:AGENT_MODEL_NAME = "your-model-name"
$env:AGENT_MODEL_API_KEY = "your-key"
& ".\.venv\Scripts\python.exe" -m market_entry_agent --workspace "$workspace" run .\examples\mission.json --engine model
```

这些环境变量仅影响当前窗口和由它启动的程序。示例域名与密钥是占位值，请换成自己的服务。应用不自动加载 `.env`。公开搜索需要单独设置支持的搜索服务与 `AGENT_SEARCH_API_KEY`，并在任务中填写允许发送的 `search_queries`；详见[联网配置](live-research.md)。

Environment variables apply to this PowerShell session and child processes. Replace placeholders with your provider settings. The app does not auto-load `.env`. Public search requires its own configuration and explicit mission queries. Company context and selected evidence go to your configured model; only explicit public queries go to search.

可选研究说明通过 `$env:AGENT_INSTRUCTIONS_FILE` 指向仓库之外的 UTF-8 文件。文件内容会发送至所配置模型，保留在本地任务检查点中。不要将真实凭据或私人资料提交到 GitHub。

For a dedicated Hermes endpoint, use its actual listener/model alias and key and follow the [Hermes guide](hermes.md). Its example configuration is independent of the product's native Windows runtime; service setup and external-provider availability must be verified in your own environment.

## 5. 保存、恢复和导出 / Reopen, resume and export

在新的 PowerShell 窗口使用前，重新进入项目目录并设置同一个 `$workspace`。把下例的任务 ID 换成 `list` 返回的值：

```powershell
& ".\.venv\Scripts\python.exe" -m market_entry_agent --workspace "$workspace" list
& ".\.venv\Scripts\python.exe" -m market_entry_agent --workspace "$workspace" show "RUN_ID"
& ".\.venv\Scripts\python.exe" -m market_entry_agent --workspace "$workspace" resume "RUN_ID"
& ".\.venv\Scripts\python.exe" -m market_entry_agent --workspace "$workspace" export "RUN_ID" --output ".\exports\研究报告.md"
& ".\.venv\Scripts\python.exe" -m market_entry_agent --workspace "$workspace" export "RUN_ID" --output ".\exports\研究报告.json"
```

输出文件为 UTF-8。已完成任务的 `resume` 返回原结果；失败任务在原有预算内复用已保存步骤。Windows 下程序停止后再复制或迁移整个工作空间，避免正在写入的数据库文件被占用。[恢复机制](runtime.md)。

Reports export as UTF-8. Resuming a completed run returns the saved result; failed runs reuse saved steps within the original budget. Stop the server and worker before copying a workspace or replacing installed files.

## 6. 显式周期任务 / Explicit recurring research

```powershell
& ".\.venv\Scripts\python.exe" -m market_entry_agent --workspace "$workspace" schedule .\examples\mission.json --engine demo --interval 3600
& ".\.venv\Scripts\python.exe" -m market_entry_agent --workspace "$workspace" worker --once
& ".\.venv\Scripts\python.exe" -m market_entry_agent --workspace "$workspace" schedules
```

`--engine demo` 仍为虚构演示；真实模型任务须自行配置服务后改为 `--engine model`。持续运行时去掉 `--once`，在单独窗口启动一个 `worker`。建立周期任务不会自动创建 Windows 服务，也不自动对外发送消息。

For unattended operation, an operator can configure Windows Task Scheduler with the venv Python's **absolute path**, module arguments, repository working directory and the same workspace. Start with a bounded `worker --once` task; verify its result in task history and avoid overlapping workers. Model configuration must be available in that task's environment. This project does not create or modify your host scheduler automatically.

## 7. 检查安装 / Verify the installation

源码目录中执行：

```powershell
& ".\.venv\Scripts\python.exe" -m unittest discover -s tests -v
& ".\.venv\Scripts\python.exe" scripts\check_public_release.py
& ".\.venv\Scripts\python.exe" scripts\check_core.py
& ".\.venv\Scripts\python.exe" scripts\verify_portability.py
```

最后一项在临时的中文与空格路径中实际执行命令行、国区查询、报告保存重开、导出、周期任务及本机 HTTP 任务，使用虚构演示，不向外联网、不调用模型。它还以旧式重定向编码启动子进程，检查中文输出。结束后清理临时目录。

The last check exercises CLI and loopback HTTP, Unicode paths, report persistence/export, explicit schedules and legacy redirected output, using no model or external network. Its JSON receipt records the actual OS and Python version. Windows CI results are linked from the repository's Actions tab; they are distinct from manual desktop/browser acceptance.

## 常见问题 / Troubleshooting

| 现象 / Symptom | 处理 / Action |
|---|---|
| `py` 不存在 / launcher missing | 安装 Python 后重新打开 PowerShell，或改用已安装解释器的完整路径 / Reopen the terminal or use the interpreter's full path. |
| 找不到模块 / module not found | 确认安装和启动用的是同一个 `.venv\Scripts\python.exe` / Use the same venv for install and run. |
| 旧式重定向后显示乱码 / legacy shell redirection | 使用 `export --output` 保存报告；应用直接输出和导出均使用 UTF-8 / Prefer the app's export command for files. |
| 端口已占用 / port already in use | 用 `serve --port 18711` 等未占用端口，并打开它打印的地址 / Select an unused port and use the printed URL. |
| 找不到之前的报告 / saved reports missing | 检查 `--workspace` 是否指向原目录 / Reuse the original workspace. |
| 安装更新时文件被占用 / files in use | 先停止自己的 server/worker，再更新；不要删除现有数据库 / Stop your server and worker before updating. |
| 文件哈希校验失败 / core hash mismatch | 从新版本重新检出；`.gitattributes` 固定源文件 LF 换行，不要关闭检查来跳过错误 / Re-check out the release with its line-ending attributes. |

代码与公共数据的开放范围见 [PUBLIC_RELEASE_POLICY.md](../PUBLIC_RELEASE_POLICY.md) 和 [LICENSE-DATA.md](../LICENSE-DATA.md)。Windows 使用同样的独立工作空间、来源与隐私边界。

Project memory, bounded context, document skills, run controls and usage receipts: [shared kernel guide](kernel.md).

Private product workflow, versioned records and public-source replay: [guide](product-workflow.md).


## 私有知识库、监测与技能学习

上述安装也包含新能力。页面按项目上传资料、预览并确认监测方案，在独立 PowerShell 窗口运行 `python -m market_entry_agent worker`。固定偏移时区如 `UTC+08:00` 不需要额外包；IANA 地区时区可能需要可选 `tzdata`。Hermes 发送须配置实际可执行文件的绝对路径，不通过 shell 执行命令；如果 Windows 的 Hermes 安装方式不提供可直接执行的程序，继续使用本地收件箱或在受支持的 Hermes 宿主运行发送适配器。服务、收件目标和模型学习均不自动启用。完整流程见[持续研究](continuous-research.md)。
