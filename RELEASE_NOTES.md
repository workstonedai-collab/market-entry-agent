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
