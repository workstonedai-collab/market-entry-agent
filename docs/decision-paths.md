# 从进入方案到验证与测算 / Entry decision paths

先说清交易由谁承担，再比较方案需要付出的成本与责任。生产地、中转地、合同卖方所在地、进口主体和目标客户市场分别记录，避免仅因为一条路线经过某国，就把它当作原产国或销售市场。

## 实际路径

1. 在已有项目中保存企业情况和进入方案。
2. 添加“交易责任”，关联方案编号，分别填写生产方、出口方、卖方、进口申报主体、客户及所在地。贸易术语未知可以留空；责任说明保留尚待确认的部分。
3. 添加“报价与测算”，使用统一币种和数量单位。每项数值标明来自操作者取得的报价还是测算假设，并写清依据；未知留空，确认为零时明确填 `0`。
4. 在“关键假设”补充是否阻断推进、对选择的影响和验证投入，并说明由谁取得什么资料、支持与不成立时怎样调整。队列先排阻断项，再看影响程度与投入；它不代表市场成功概率。
5. 新资料匹配某条假设后，查看关联方案、阶段和决策编号，以及前后状态。新的报价会保存测算前后差异；已有选择继续保留，由操作者决定是否调整。

Models read the frozen transaction records, deterministic calculations and validation priorities through `project_state`. They cannot modify quote inputs, transaction responsibility, selected options, confirmed progress or operator decisions. The report still saves directly, with proposed actions and stated conditions.

## 测算口径

One scenario uses one three-letter currency. There is no automatic exchange-rate conversion or inferred tax rate. All monetary inputs are whole-scenario amounts except `unit_price` and `unit_cost`; quantity uses the stated `unit`. `duty_rate` is a fraction, e.g. `0.05`, and `customs_value` is the operator's explicit whole-scenario customs base with its own valuation note. An Incoterm alone does not populate any price or customs base.

```text
revenue = quantity × unit_price
product cost = quantity × unit_cost
duty = customs_value × duty_rate
operating cost = product cost + freight + insurance + duty + channel_fee + fixed_cost
contribution before other costs = revenue − operating cost
cash outlay = operating cost + recoverable_tax
```

可抵扣税款单列现金占用，不当作已确认费用重复扣除。贡献额还没有计入未列出的费用，不等于企业净利润。依赖项缺失时，相关结果保留 `null`；仍能计算的其他项目继续展示。使用十进制定点运算，避免二进制浮点累加误差；页面按两位小数展示，导出保留计算原值；展示金额不能作为税务申报口径。

`economics` JSON commands use the existing `project-save`/`POST /api/project` interface:

```json
{"kind":"economics","id":"trial-quote","expected_revision":0,"data":{"option_id":"saved-option-id","name":"Fictional trial quotation","currency":"USD","unit":"units","values":{"quantity":{"value":"100","basis":"assumption","note":"Illustrative trial quantity"},"unit_price":{"value":"20","basis":"assumption","note":"Illustrative selling price"},"unit_cost":{"value":"10","basis":"assumption","note":"Illustrative product cost"},"freight":null}}}
```

Unlisted input items remain unknown. Supported keys are `quantity`, `unit_price`, `unit_cost`, `freight`, `insurance`, `customs_value`, `duty_rate`, `channel_fee`, `fixed_cost`, `recoverable_tax`. `basis` is `operator_quote` or `assumption`; neither means the software independently verified the figure. Values must be finite and nonnegative, quantity positive, and duty rate between 0 and 1.

## 新证据怎样改变选择

The [CBAM public replay](../examples/public-project-case.json) retains attributed historical announcement summaries and fictional company conditions. New behavior tests show that the later source marks the linked premise for research and identifies its related decision; it does not decide legal applicability or automatically reverse the chosen route. A synthetic quotation test changes freight from 100 to 200 USD, showing contribution moving from 680 to 580 USD while the prior selection and original scenario revision remain available.

通用研究步骤和公开测算公式保留开源。专用提示词、私有研究知识、客户资料及内部研发材料不随项目发布；需要进一步交流可[联系作者](https://github.com/workstonedai-collab)。
