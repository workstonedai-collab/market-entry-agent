# 集成取舍与参考 / Integration references

本轮先补资料导入、工作成果交付和按任务组织研究。保留现有运行器、预算与直接保存报告的路径，不整体替换技术栈。以下依据本轮 GitHub 仓库说明与许可证信息，项目声称的效果不当作本项目的实测结论。

| 项目 | 查看时许可证 | 本轮采用方式 |
|---|---|---|
| [iOfficeAI/OfficeCLI](https://github.com/iOfficeAI/OfficeCLI) | Apache-2.0 | 可选本地进程集成；v1.0.158 的 DOCX 创建与段落写入，不捆绑其二进制或安装器 |
| [microsoft/markitdown](https://github.com/microsoft/markitdown) | MIT | 可选隔离 Python 适配器，读取本机 DOCX/XLSX/PPTX，关闭插件，不配置模型 |
| [revfactory/harness](https://github.com/revfactory/harness) | Apache-2.0 | 借鉴领域任务、输入输出契约和按需加载的组织方法；未复制代码或安装 Claude Code 插件，未接入其团队运行机制 |
| [asgeirtj/system_prompts_leaks](https://github.com/asgeirtj/system_prompts_leaks) | 仓库标注 CC0-1.0 | 作为提示结构观察材料；收录文本的来源、版本与第三方权利不能仅凭仓库标签推定，不整段复制或运行收录提示词 |
| [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) | MIT | 借鉴任务与上下文管理、按需技能；本轮未引入其依赖或替换现有执行器 |
| [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | Apache-2.0 | 借鉴按问题取材、保留来源和导出成果；本轮未集成其模型调用与并行运行器 |

同名 [officecli/officecli](https://github.com/officecli/officecli) 是另一个文档生成项目，其说明包含托管试用、模型配置和可选发布；本轮选用上表的 iOfficeAI 本地工具，不调用同名服务。

以上为接口集成或独立实现的设计借鉴；未把第三方原始代码、提示词或许可证文本混入本项目 MIT 源码。部署时应保留所安装第三方组件各自的许可与说明。配置接入、测试通过、模型分析质量和生产托管分别记录，不互相替代。

## 后续按使用反馈推进

办公接线完成后，继续围绕专题研究、报道准备、利益观察，以及市场选择、交易评估、经营跟踪改进来源和成果形式。当前 DOCX 导出以完整文字为先；Word 排版模板、PPTX/XLSX 成果导出和更多外部数据服务尚未实现。不会因参考项目带有多智能体或审稿流程，就默认增加模型调用或改变直接交付方式。


## 持续研究与学习的参考

本次借鉴 [Hermes Skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills) 的按需技能与经验整理，以及 [Cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron) 的调度、执行、交付分离和静默机制；参考 [Letta Code](https://github.com/letta-ai/letta-code) 的长期状态与版本管理、[Mem0](https://github.com/mem0ai/mem0) 的有范围记忆、[LightRAG](https://github.com/HKUDS/LightRAG) 的资料版本与引用、[changedetection.io](https://github.com/dgtlmoon/changedetection.io) 的有效变化筛选，以及 [Dify](https://github.com/langgenius/dify) 的导入与处理状态体验。这里复用设计经验，没有打包这些 SDK、模型、提示词或私有内容；Hermes CLI 发送适配器是可选的独立安装。向量/图谱、模型权重训练与完整知识平台不属于本版。见[当前功能与边界](continuous-research.md)。
