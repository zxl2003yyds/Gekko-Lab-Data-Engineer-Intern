# Q4 冻结样本评估与人工复核入口

## 样本和评审来源

评估样本为冻结规则后选取的 60 条非空唯一正文，固定 seed=20261105，并按原文 SHA-256 排除全部开发文本及其重复记录。样本后来用于事后语义分析；若据此修改规则，需要另建未见测试集。评估单位是独立文本，不按出现次数加权，结果不直接代表全平台准确率。

参考类别由当前助手在查看最终预测前根据原文填写。开发与评审仍由同一助手参与，存在共同偏差；这是助手参考标签一致率，不是独立人工准确率。真实人工语义准确率、翻译准确率与幻觉率尚未测得。

初版 30 条样本及第一轮新增 60 条样本已转为开发资料，不再作为未见测试。开发过程曾暴露退款和商品未收到混淆等问题，修正后另取本次样本。旧规则 rules_v1.py 保留用于同样本基线重算；早期过程快照仅在本地保留。

## 同一最终样本上的比较

| 版本 | 类别集合完全一致 | 微平均 precision | 微平均 recall | TP / FP / FN |
| --- | --- | --- | --- | --- |
| v1 | 14/60 | 92.31% | 17.91% | 12 / 1 / 55 |
| pt-rules-v2 | 24/60 | 82.35% | 41.79% | 28 / 6 / 39 |

| 类别 | TP | FP | FN |
| --- | --- | --- | --- |
| delivery_late | 2 | 0 | 3 |
| missing_item | 15 | 0 | 11 |
| other | 4 | 3 | 13 |
| packaging | 0 | 0 | 0 |
| quality_defect | 3 | 0 | 4 |
| seller_communication | 0 | 3 | 2 |
| wrong_product | 4 | 0 | 6 |

precision 只衡量抽出类别的正确比例，recall 衡量漏掉多少参考类别；两者必须一起看。样本较小，而且参考标签不是独立真值，不能据此承诺生产效果。条件性退款请求、仅表示等待回复和笼统不满的分类仍可能存在歧义。

## 逐条结果与复核材料

evaluation_review_pack.json 包含全部 60 条原文、参考标签、歧义说明和实际预测（含严重度、短语英译、上下文及置信度），可逐条检查，不只是看一个总分。

| 源记录号 | 参考类别 | 当前类别 | 说明 |
| --- | --- | --- | --- |
| 15288 | other, quality_defect | other | 商品损坏，退货申请被拒；拒绝不是未回复。 |
| 95386 | other | other | 运费贵还要邮局自取。 |
| 80785 | 无 | 无 | 明确好评。 |
| 94005 | seller_communication, wrong_product | wrong_product | 发错货，邮件未回复。 |
| 17732 | missing_item | missing_item | 买二收一。 |
| 71422 | missing_item | 无 | 另一商品尚未到，存在拼写错误。 |
| 11810 | missing_item | other | 买两件只收到一件。 |
| 48681 | wrong_product | 无 | 不是下单的商品；完好不代表没发错。 |
| 72677 | 无 | 无 | 查询是否取消，未陈述明确投诉。 |
| 74733 | quality_defect | 无 | 鞋垫有问题；等待供应商联系不直接认定已失联。 |
| 19847 | wrong_product | 无 | 碳粉型号 CB435A 与订购 CB436A 不符。 |
| 50194 | other | other | 对配送不满意，未说明是否迟到。 |
| 34946 | quality_defect | 无 | 麦克风不工作、声音异常。 |
| 19882 | quality_defect | quality_defect | 产品不工作。 |
| 78379 | quality_defect | quality_defect | 镜子质量差；退货退款是补救请求，不另推断退款故障。 |
| 89152 | missing_item | seller_communication | 只送一半；请求回复本身不直接认定失联。 |
| 88853 | other | 无 | 临近期限才要求远距离自取，导致未取到货。 |
| 90447 | delivery_late, missing_item | delivery_late, other | 超过期限仍未收到；退款为条件性的后续请求。 |
| 53792 | missing_item | missing_item | 买三收一。 |
| 71403 | delivery_late | 无 | 付款后延后承诺时间，实际仍晚两天。 |
| 94163 | missing_item | missing_item | 付了两件的钱，只收到一件。 |
| 36992 | missing_item | 无 | 缺少背包。 |
| 21415 | missing_item | 无 | 四件只收到两件。 |
| 19872 | missing_item | missing_item | 两瓶香水只到一瓶。 |
| 3166 | 无 | 无 | 店铺可靠，曾经回购。 |
| 36313 | missing_item, wrong_product | seller_communication | 两件原装墨盒只收到一件兼容墨盒；等待邮件回复尚未证明失联。 |
| 31359 | wrong_product | 无 | 模具尺寸及适配炸锅型号不符。 |
| 40022 | delivery_late, missing_item, other | delivery_late, missing_item | 开票慢、明确超过日期且商品未到。 |
| 5765 | delivery_late, seller_communication | 无 | 配送慢，缺少邮件跟踪信息。 |
| 57364 | missing_item | missing_item | 错误流转到别州，至今未到家。 |
| 98086 | other | 无 | 未满足预期，未说明具体质量缺陷；实际提前送达。 |
| 7918 | wrong_product | 无 | 颜色不符。 |
| 56551 | missing_item | missing_item, other | 买两壶收一壶，退款或补发是补救请求。 |
| 66558 | other | 无 | 不再购买的负面意见，原因未说明。 |
| 21612 | missing_item | missing_item | 仍未收到。 |
| 56797 | 无 | 无 | 感谢，无投诉。 |
| 19155 | missing_item, other | missing_item | 商品及退款均未收到。 |
| 66078 | 无 | 无 | 希望更快，但明确按时且商品正确。 |
| 44885 | quality_defect | 无 | 材料不好。 |
| 13161 | other, wrong_product | wrong_product | 发错型号，想换但没有库存。 |
| 58721 | other | 无 | 质疑原装 HP 身份；这是买家的指控，未独立核实。 |
| 31377 | other | other | 不符个人预期，希望退货；对材料和交付不作负面推断。 |
| 64521 | missing_item | missing_item | 未收到全部商品但状态称已送达。 |
| 50977 | missing_item | missing_item | 未收到商品。 |
| 5592 | missing_item | missing_item | 未交付。 |
| 93983 | other | 无 | 以为材质是橡胶而非塑料，未证明广告承诺不符。 |
| 83559 | wrong_product | wrong_product | 遥控器品牌型号不符。 |
| 61066 | missing_item | missing_item | 未收到，未确定责任方。 |
| 87295 | other | 无 | 难过失望的泛泛负面情绪。 |
| 88408 | missing_item | 无 | 只收到部分，缺书。 |
| 90314 | other | 无 | 抱怨耗时，未明确是配送还是其他环节。 |
| 67174 | other | 无 | 缺购物小票。 |
| 55444 | delivery_late, missing_item | 无 | 到今天仍没到，提及已经过去的预计日期。 |
| 77864 | wrong_product | seller_communication | 明显与网站展示不同。 |
| 6341 | quality_defect, wrong_product | quality_defect, wrong_product | 不及广告所述，质量差。 |
| 55871 | missing_item | missing_item | 未收到，给出计划日期但没有评价当天日期，不确定是否已经超期。 |
| 52770 | missing_item, other | 无 | 未收到，商品在邮局且须自取。 |
| 51500 | missing_item | missing_item | 未收到商品。 |
| 73576 | missing_item | 无 | 只到了两件，其他已选购商品未到。 |
| 41239 | other | 无 | 广告易误导；店家处理正常。 |

## 严重程度、证据与翻译

字段类型、有限数值、枚举、来源记录和引文子串全部校验。输出标记 evidence_scope=phrase，evidence_contexts 补齐其所在原句；同一短语多次出现时保留所有上下文。短语英译不是整句人工翻译，个别模板仍是释义。结构通过不能证明否定、时间、责任或全部问题都判断正确。

severity、sentiment_score 和 confidence 均为明确规则下的启发值，未校准。一般未收到及无法使用记 high，体验问题记 medium，泛泛情绪记 low；并非真实损失估计。空文和未知的 sentiment_score=0 是未知占位，不表示中立。

全量 22,754 行完整留存，10,477 行标为待复核；未标记也不代表获得人工批准。外部模型调用为 0。

## 独立人工验收步骤

运行 review_campaign.py prepare，将生成的 reviewer_a_annotations.json 与 semantic_review/reviewer_instructions.md 交给审核者；这两份材料不含参考答案。协调文件和案例答案不随盲审包提供。先完成全部 30 条预选原文盲标，再审核封存版本对应的完整译文。分类指标、语义分歧和翻译错误分别报告；可选第二人复核，分歧需真人裁决。未完成这一步，不发布人工准确率。

快照校验会拒绝输出摘要、规则版本或冻结规则摘要不一致的评估；文件逐个原子替换，跨文件不是事务，中断后重跑即可。

复现：`python run_all.py --stage q4 --offline`。规则评估不发起任何网络请求。

## 后续语义深挖（不计入以上冻结成绩）

semantic_review/casebook.md 和 cases.json 补充这 60 条的事后语义草稿、完整原文英译与歧义解释。草稿纠正两处旧参考标签，但不覆盖本报告的冻结评估。完整翻译不是全数据集的新自动模型结果，也未获独立人工验收。

review_campaign.py 提供先盲标原文、后审核译文的两阶段流程；该工具在 30 条预选样本全部完成后计算相应指标。B 包用于可选第二人复核；程序保存分歧，不自动裁决。详见 semantic_review/guidelines.md。

## 本人辅助复核

另有 11 条歧义样本由项目负责人借助 Google 翻译 完成辅助复核。其中 9 条选择译文忠实，2 条未填写译文判断。这些记录不是随机总体样本或独立葡英审核，不用于计算上述冻结成绩和独立人工准确率。

来源行号、原文摘要及本人选择见 owner_review_summary.json；完整网页进度和学习界面仅在本地保留。
