# 语义裁决与独立复核说明

这份材料补充 Q4 的语义层。当前有 60 条完整原文翻译、逐条问题草稿和可执行复核工具。全部翻译由当前助手撰写，尚无独立人工验收；原来的冻结规则、全量 JSON 和基准成绩保持原样。

## 先拆事实，再确定问题

按“对象—行为—时间—语气”读一句话，不只搜关键词。对象可能是商品、退款、发票、回复或物流状态；行为可以已经发生、尚未发生、被否定，或只是期望与条件。一个投诉可以包含多个事实，但补救请求不能重复当作新的故障。

| 情况 | 本轮口径 | 真实案例 |
| --- | --- | --- |
| 买两件只收到一件 | missing_item；数量比较跨从句进行，包裹数量不等于商品数量 | 17732、11810 |
| 收到型号 CB435A，订购 CB436A | wrong_product；逐字符保留两个型号 | 19847 |
| “如果还不到，我要退款” | 当前未到/迟到可标，退款是有条件的后续动作 | 90447 |
| “商品和退款都没收到” | missing_item 与 other 两个实际问题 | 19155 |
| “我在等回复” | 记录 contact 请求；单靠等待不能证明客服失联 | 89152 |
| “已经发邮件，但没回复” | seller_communication 有明确依据 | 94005 |
| “商品不是我订的，但很完好” | wrong_product；完好不消除错货 | 48681 |
| 提前到两件，但还有其他商品没到 | missing_item；不能因为有“提前”就判整单正常 | 73576 |
| 希望更快，但明确按时到 | 不标 delivery_late | 66078 |
| 质量不及广告、未说明型号差异 | quality_defect；不自动再加 wrong_product | 6341 |
| 只给预计日，没有今天日期 | 不直接断言已经超期；保留时间歧义 | 55444、55871 |
| 包装看似原装，但打印机说不是 HP | 保留买家报告和说话主体，不写成平台鉴定结论 | 58721 |

`missing_item` 在本项目中同时覆盖整单尚未收到和部分缺件；如实际业务只允许“部分缺件”，应先拆分类别再重新标注，不能在一半样本中改变定义。`other` 包含明确但不属前六类的投诉及无具体原因的负面意见；单纯查询状态不是投诉。质量轻重与主观不喜欢必须区别。

严重程度：明确完全不能使用或缺少商品通常为 high；错型号、一般质量、服务及履约问题通常为 medium；无具体损害的笼统负面意见为 low。不能把词语激烈程度直接当经济损失。`actionable_for_seller` 只说明卖家可调查、联系或处理，不等于认定责任在卖家。情绪单列 positive/negative/mixed/unknown，没有虚构新置信度。

## 翻译必须保留的内容

1. **否定和对象**：not received a refund 不能变成 not received the product；not very good 不能加强成 terrible。
2. **数量和型号**：买、到、缺三个数量分开；保留前导零、CB436A/CB435A、HP670XL、日期和价格。
3. **时间与条件**：if、still、already、after 的关系保留；不得为 27/08 添加年份，也不得根据当前日期判断历史订单。
4. **说话主体**：消费者的指控、打印机提示、商家告知与已证实事实不能互换。
5. **完整范围**：本轮 evidence_quote 是完整源评价，英文翻译对应整个范围。原文若本来残缺，不补写未提供的内容。语法纠正和疑似错词解释写入 notes。
6. **有歧义的词**：`mocho` 的词典义既有鸟类也有无靠背凳；本案例关联商品属于办公家具，因此翻译为 stools，并保存辅助语境。没有证据把它进一步称为牙科凳。[Priberam 词义](https://dicionario.priberam.org/mocho)。

数字/实体保留检查只验证字符串，不能证明翻译忠实。完整译文应由能读葡语与英语的人检查遗漏、增译、语气强度及主体。

## 为什么不把修订后的草稿再报成高准确率

这 60 条文本已被阅读、解释和修订，属于事后分析。原参考标签本身也有两个保守性修订（55444、6341），因此它不是永远正确的标准答案。`cases.json` 是候选改进材料，不会自动覆盖 `extracted_issues.json`，不会进入原规则的测试真值，也不声称推广到另外一万余条不同文本。下一版自动算法应另留未见文本测试。

## 可执行人工复核流程

在项目根目录执行：

```bash
.venv/bin/python -m q4_llm_extraction.build_semantic_review
.venv/bin/python -m q4_llm_extraction.review_campaign prepare
```

第二条打印活动目录。目录名由冻结案例内容计算；相同内容复用，已填写文件不会被重置。用下面命令时把 `CAMPAIGN_PATH` 替换成打印出的实际目录。

**阶段一：原文盲标。** 将 `reviewer_a_annotations.json` 及不含样本答案的英文说明 `reviewer_instructions.md` 交给未参与代码/草稿制作、具备葡英能力的真人。先不要交本说明、casebook、译文或 coordinator_snapshot，因为它们包含具体案例的参考决策。审核者如实填写 attestation；程序要求完成 `primary_30=true` 的全部共同 30 条，不可自行换成容易样本，建议全部 60 条。每条填写问题类别、严重度、原文证据、情绪、可行动性和说明。`issues=null` 表示未审，`issues=[]` 表示审过且未发现问题。问题项格式：

```json
{"category":"missing_item","severity":"high","evidence_quote":"从该条原文逐字复制的证据"}
```

**阶段二：译文审核。** 第一阶段至少完成 30 条后运行：

```bash
.venv/bin/python -m q4_llm_extraction.review_campaign prepare-translation --campaign CAMPAIGN_PATH --reviewer a
```

程序封存第一阶段文件，并产生带其摘要的翻译包。审核者填 `faithful`、`minor_error` 或 `major_error`；有错误时同时填写错误类型和修订译文。改动原标注会使旧翻译包失配，须生成新版本；旧版保留。

**阶段三：计算结果。** 用打印出的翻译包路径替换 `TRANSLATION_FILE`：

```bash
.venv/bin/python -m q4_llm_extraction.review_campaign assess --campaign CAMPAIGN_PATH --reviewer a --translation TRANSLATION_FILE
```

报告分别比较冻结规则与语义草稿的类别精确率/召回率，列出严重度、情绪、可行动性的差异，以及译文错误。只有审核样本无上述差异且译文均忠实时，才标为 `accepted_for_reviewed_sample`；它只适用于审过的样本，不是整个数据集验收。其他情况保持 `changes_required`。

可选第二位真人独立填写 B 包；不要把 A 答案交给 B。评估时增加 `--second-annotations B_FILE`，报告共同样本与分歧，有分歧则 `requires_human_adjudication`。此工具不会自动抹平分歧或假造第三位裁决者；需由真人讨论并记录裁决，后续草稿另建版本。

独立盲审尚无真实人工提交，状态为 `awaiting_independent_human_review`，人工指标为 null。软件只能检查声明和数据一致性，不能验证审核者身份、语言能力或是否偷看其他文件；独立性还需要流程管理。工具也不会自动找人、发送评价、付费或调用其他模型。

## 本人辅助复核

另有 11 条歧义样本由本人借助 Google 翻译和中文辅助材料完成判断，摘要见 `../owner_review_summary.json`。这些记录不属于独立盲审，不改变其状态或准确率。学习网页、完整进度和历史自检快照仅在本地保留。
