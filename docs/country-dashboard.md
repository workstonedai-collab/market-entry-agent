# 国区公共数据 / Public country observations

在看板中查找国区，查看 WGI 治理分项、B-READY营商支柱与主题、来源期次和覆盖情况；对照最多五个国家，将所选国家带入研究任务。数据展示来源原始分项，并提供已公开的研究参考计算；不同覆盖保持区分，不输出国家排名。缺失保持为空。

- World Bank WGI 2026 Update，2025年观测：[官方目录](https://datacatalog.worldbank.org/infrastructure-data/search/dataset/0038026/worldwide-governance-indicators)。215个经济体有分项，206个有完整六维。
- World Bank B-READY 2025：[官方数据](https://www.worldbank.org/en/businessready/data)。本快照中101个经济体有三支柱与十主题。
- 快照日期2026-10-21。统计年份与快照取得日期不同；WGI区间来自来源，不用于推导国家排名或当前事件。保留单元格位置、文件哈希和署名。

```bash
market-entry-agent --workspace ./workspace country-list
market-entry-agent --workspace ./workspace country Vietnam
market-entry-agent --workspace ./workspace compare Vietnam Indonesia
```

`country_baseline` 返回任务范围内的公共记录ID，模型读取后可引用。历史时点早于快照可用日期时不使用该快照。网页和CLI导出只包含所选来源分项。

公开复现只需官方工作簿及开发依赖 `openpyxl`：

```bash
python scripts/build_country_data.py --wgi wgi2026.xlsx \
  --bready 01_B-READY-2025-PILLAR-TOPIC-SCORES.xlsx \
  --as-of 2026-10-21 --output observations.json
```

The bundled source observations include coverage, units, source intervals and periods. The source components, research-reference formula and weights are public; no country ranking is supplied. The snapshot works without a search or model key. See [data terms](../LICENSE-DATA.md).

## 公开的研究参考公式

完整双源：`0.60 × B-READY三支柱均值 + 0.40 × WGI六维均值`。只有完整WGI时显示六维均值，并标为单源观察；治理维度不足六个时不生成总值。十个B-READY主题用于展示，不重复计权。使用源值精度计算，展示时四舍五入；贡献明细可复算。

权重为研究选择，未校准预测效度；该合成不是世界银行官方指数，也不能替代企业或项目判断。源级区间不能视为合成总值区间，近期事件不自动改变年度结构值。

研究提纲公开宏观、行业、竞争与进入路径等一般研究步骤，输出可使用拟议行动阶段与观察条件。专用提示词和部分进一步研究方法暂未开源，可[联系作者](https://github.com/workstonedai-collab)交流。
