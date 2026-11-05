"""比较冻结规则与 v1 在同一组未见文本上的结果，不冒充人工准确率。"""

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from download_data import ROOT
from q1_data_quality.q1_code import table
from q4_llm_extraction.io_utils import atomic_write_text
from q4_llm_extraction.rules import CATEGORIES, VERSION
from q4_llm_extraction.rules_v1 import extract_text as baseline_extract


def score_labels(expected, predicted):
    if set(expected) != set(predicted):
        raise ValueError('参考标签与预测的记录键不一致')
    counts = {name: Counter(tp=0, fp=0, fn=0) for name in sorted(CATEGORIES)}
    exact = 0
    for key, reference in expected.items():
        actual = predicted[key]
        exact += actual == reference
        for name in reference & actual:
            counts[name]['tp'] += 1
        for name in actual - reference:
            counts[name]['fp'] += 1
        for name in reference - actual:
            counts[name]['fn'] += 1
    tp, fp, fn = (sum(c[name] for c in counts.values()) for name in ('tp','fp','fn'))
    return {'sample_size':len(expected), 'exact':exact, 'tp':tp, 'fp':fp, 'fn':fn,
            'precision':tp/(tp+fp) if tp+fp else None, 'recall':tp/(tp+fn) if tp+fn else None,
            'by_category':{k:dict(v) for k,v in counts.items()}}


def unique_index(rows, key):
    result = {row[key]:row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f'重复的记录键：{key}')
    return result


def validate_snapshot(content, manifest, design, rules_bytes):
    if hashlib.sha256(content).hexdigest() != manifest['output_sha256']:
        raise ValueError('输出与运行清单的摘要不符，请重跑 Q4 后评估')
    if manifest['version'] != VERSION:
        raise ValueError('输出版本与当前规则不一致')
    if hashlib.sha256(rules_bytes).hexdigest() != design['frozen_rule_sha256']:
        raise ValueError('规则在冻结评估集后发生变化；请重新隔离未见评估集')


def evaluate():
    folder = ROOT/'q4_llm_extraction'
    audit = ROOT/'.local/q4'
    design = json.loads((folder/'evaluation_design.json').read_text())
    label_document = json.loads((folder/'evaluation_labels.json').read_text())
    labels = unique_index(label_document['labels'], 'source_row')
    samples = unique_index(json.loads((audit/'evaluation_holdout.json').read_text()), 'source_row')
    content = (folder/'extracted_issues.json').read_bytes()
    manifest = json.loads((audit/'metrics.json').read_text())
    validate_snapshot(content, manifest, design, (folder/'rules.py').read_bytes())
    all_predictions = unique_index(json.loads(content), 'source_row')
    if set(samples) != set(labels) or not set(samples) <= set(all_predictions):
        raise ValueError('评估样本、标签或输出记录不一致')
    if len({row['text'] for row in samples.values()}) != len(samples):
        raise ValueError('当前评估单位为唯一正文，不允许重复原文')
    if any(not r['text'].strip() or hashlib.sha256(r['text'].encode()).hexdigest() in design['development_text_sha256'] for r in samples.values()):
        raise ValueError('评估文本为空或与开发集重合')
    expected = {k:set(row['categories']) for k,row in labels.items()}
    if any(not value <= CATEGORIES for value in expected.values()):
        raise ValueError('未知参考类别')
    predicted = {k:{i['category'] for i in all_predictions[k]['issues']} for k in expected}
    old = {k:{i['category'] for i in baseline_extract(samples[k]['text'])[0]['issues']} for k in expected}
    current, baseline = score_labels(expected,predicted), score_labels(expected,old)
    metrics = {'version':VERSION,'current':current,'baseline_v1':baseline,
               'rules_sha256':design['frozen_rule_sha256'],'output_sha256':manifest['output_sha256'],
               'labels_sha256':hashlib.sha256((folder/'evaluation_labels.json').read_bytes()).hexdigest(),
               'reviewer':label_document['reviewer'],'sampling_unit':design['sampling_unit']}
    atomic_write_text(audit/'evaluation_metrics.json',json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
    pack = [{'source_row':k,'text':samples[k]['text'],'reference_categories':sorted(expected[k]),
             'reference_note':labels[k]['note'],'prediction':all_predictions[k]} for k in labels]
    atomic_write_text(folder/'evaluation_review_pack.json',json.dumps(pack,ensure_ascii=False,indent=2)+'\n')
    # 供另一人盲审的空白表不预填助手标签或预测，避免锚定。
    blank = [{'source_row':k,'text':samples[k]['text'],'reviewer':None,'issues':None,
              'sentiment_score':None,'actionable_for_seller':None,'notes':None} for k in labels]
    # 兼容旧入口，已填写的早期人工记录也不能被重跑清空。
    if not (audit/'manual_review_template.json').exists():
        atomic_write_text(audit/'manual_review_template.json',json.dumps(blank,ensure_ascii=False,indent=2)+'\n')
    def percent(value):
        return f'{value:.2%}' if value is not None else '未定义'
    report = ['# Q4 冻结样本评估与人工复核入口',
        '## 样本和评审来源',
        '评估样本为冻结规则后选取的 60 条非空唯一正文，固定 seed=20261105，并按原文 SHA-256 排除全部开发文本及其重复记录。样本后来用于事后语义分析；若据此修改规则，需要另建未见测试集。评估单位是独立文本，不按出现次数加权，结果不直接代表全平台准确率。',
        '参考类别由当前助手在查看最终预测前根据原文填写。开发与评审仍由同一助手参与，存在共同偏差；这是助手参考标签一致率，不是独立人工准确率。真实人工语义准确率、翻译准确率与幻觉率尚未测得。',
        '初版 30 条样本及第一轮新增 60 条样本已转为开发资料，不再作为未见测试。开发过程曾暴露退款和商品未收到混淆等问题，修正后另取本次样本。旧规则 rules_v1.py 保留用于同样本基线重算；早期过程快照仅在本地保留。',
        '## 同一最终样本上的比较',
        table(['版本','类别集合完全一致','微平均 precision','微平均 recall','TP / FP / FN'],[
            ['v1',f"{baseline['exact']}/60",percent(baseline['precision']),percent(baseline['recall']),f"{baseline['tp']} / {baseline['fp']} / {baseline['fn']}"],
            [VERSION,f"{current['exact']}/60",percent(current['precision']),percent(current['recall']),f"{current['tp']} / {current['fp']} / {current['fn']}"]]),
        table(['类别','TP','FP','FN'],[[name,*[count[k] for k in ('tp','fp','fn')]] for name,count in current['by_category'].items()]),
        'precision 只衡量抽出类别的正确比例，recall 衡量漏掉多少参考类别；两者必须一起看。样本较小，而且参考标签不是独立真值，不能据此承诺生产效果。条件性退款请求、仅表示等待回复和笼统不满的分类仍可能存在歧义。',
        '## 逐条结果与复核材料',
        'evaluation_review_pack.json 包含全部 60 条原文、参考标签、歧义说明和实际预测（含严重度、短语英译、上下文及置信度），可逐条检查，不只是看一个总分。',
        table(['源记录号','参考类别','当前类别','说明'],[[k,', '.join(sorted(expected[k])) or '无',', '.join(sorted(predicted[k])) or '无',labels[k]['note']] for k in labels]),
        '## 严重程度、证据与翻译',
        '字段类型、有限数值、枚举、来源记录和引文子串全部校验。输出标记 evidence_scope=phrase，evidence_contexts 补齐其所在原句；同一短语多次出现时保留所有上下文。短语英译不是整句人工翻译，个别模板仍是释义。结构通过不能证明否定、时间、责任或全部问题都判断正确。',
        'severity、sentiment_score 和 confidence 均为明确规则下的启发值，未校准。一般未收到及无法使用记 high，体验问题记 medium，泛泛情绪记 low；并非真实损失估计。空文和未知的 sentiment_score=0 是未知占位，不表示中立。',
        f"全量 {manifest['rows']:,} 行完整留存，{manifest['needs_review']:,} 行标为待复核；未标记也不代表获得人工批准。外部模型调用为 0。",
        '## 独立人工验收步骤',
        '运行 review_campaign.py prepare，将生成的 reviewer_a_annotations.json 与 semantic_review/reviewer_instructions.md 交给审核者；这两份材料不含参考答案。协调文件和案例答案不随盲审包提供。先完成全部 30 条预选原文盲标，再审核封存版本对应的完整译文。分类指标、语义分歧和翻译错误分别报告；可选第二人复核，分歧需真人裁决。未完成这一步，不发布人工准确率。',
        '快照校验会拒绝输出摘要、规则版本或冻结规则摘要不一致的评估；文件逐个原子替换，跨文件不是事务，中断后重跑即可。',
        '复现：`python run_all.py --stage q4 --offline`。规则评估不发起任何网络请求。']
    report += ['## 后续语义深挖（不计入以上冻结成绩）',
        'semantic_review/casebook.md 和 cases.json 补充这 60 条的事后语义草稿、完整原文英译与歧义解释。草稿纠正两处旧参考标签，但不覆盖本报告的冻结评估。完整翻译不是全数据集的新自动模型结果，也未获独立人工验收。',
        'review_campaign.py 提供先盲标原文、后审核译文的两阶段流程；该工具在 30 条预选样本全部完成后计算相应指标。B 包用于可选第二人复核；程序保存分歧，不自动裁决。详见 semantic_review/guidelines.md。']
    owner_path = folder / 'owner_review_summary.json'
    if owner_path.exists():
        owner = json.loads(owner_path.read_text(encoding='utf-8'))
        report += ['## 本人辅助复核',
            f"另有 {owner['reviewed_count']} 条歧义样本由项目负责人借助 {owner['translation_tool']} 完成辅助复核。"
            f"其中 {owner['translation_faithful_count']} 条选择译文忠实，{owner['translation_unfilled_count']} 条未填写译文判断。"
            '这些记录不是随机总体样本或独立葡英审核，不用于计算上述冻结成绩和独立人工准确率。',
            '来源行号、原文摘要及本人选择见 owner_review_summary.json；完整网页进度和学习界面仅在本地保留。']
    atomic_write_text(folder/'accuracy_evaluation.md','\n\n'.join(report)+'\n')
    return metrics


if __name__=='__main__':
    print(json.dumps(evaluate(),ensure_ascii=False,indent=2))
