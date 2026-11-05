"""把当前助手的逐条语义草稿编成完整证据/翻译案例，不改写冻结的自动预测。"""
from collections import Counter
import csv
import hashlib
import json
import logging
from pathlib import Path

from download_data import ROOT, load_sources, validate_file
from q4_llm_extraction.extract_reviews import read_reviews
from q4_llm_extraction.io_utils import atomic_write_text
from q4_llm_extraction.rules import CATEGORIES

FOLDER = ROOT / 'q4_llm_extraction' / 'semantic_review'


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def compile_cases(annotations, sources, predictions, references):
    if annotations.get('review_status') != 'assistant_draft_pending_independent_human_review':
        raise ValueError('本编译器只接收明确标为助手草稿的材料')
    ids = [entry['source_row'] for entry in annotations['cases']]
    if len(ids) != len(set(ids)):
        raise ValueError('语义草稿来源行号重复')
    result = []
    for entry in annotations['cases']:
        key = entry['source_row']
        source = sources[key]
        text = source['review_comment_message']
        if digest(text) != entry['source_text_sha256']:
            raise ValueError(f'原文版本变化：{key}')
        english = entry['translation_en']
        if not isinstance(english, str) or not english.strip():
            raise ValueError(f'英文翻译为空：{key}')
        for literal in entry['protected_literals']:
            if literal not in text or literal not in english:
                raise ValueError(f'关键数字/实体未逐字保留：{key} {literal}')
        issues = []
        for item in entry['issues']:
            if item['category'] not in CATEGORIES or item['severity'] not in {'low','medium','high'}:
                raise ValueError('未知类别或严重程度')
            # 用完整的源评价作为证据，避免只截取一句中的否定或条件部分。
            issues.append({**item, 'evidence_quote':text, 'evidence_quote_en':english})
        categories = {issue['category'] for issue in issues}
        if len(categories) != len(issues):
            raise ValueError('同一草稿中的问题类别重复')
        if entry['sentiment_label'] not in {'positive','negative','mixed','unknown'}:
            raise ValueError('情绪标签非法')
        if type(entry['actionable_for_seller']) is not bool:
            raise ValueError('actionable_for_seller 必须为布尔值')
        original = predictions[key]
        if original['review_id'] != source['review_id'] or original['order_id'] != source['order_id']:
            raise ValueError('冻结预测与来源记录不一致')
        result.append({
            'source_row':key, 'review_id':source['review_id'], 'order_id':source['order_id'],
            'source_text_sha256':entry['source_text_sha256'], 'source_text':text,
            'translation_en':english, 'issues':issues,
            'sentiment_label':entry['sentiment_label'], 'actionable_for_seller':entry['actionable_for_seller'],
            'requested_actions':entry['requested_actions'], 'analysis_zh':entry['analysis_zh'],
            'uncertainties':entry['uncertainties'], 'protected_literals':entry['protected_literals'],
            'translation_context':entry.get('translation_context'),
            'rule_categories':sorted(issue['category'] for issue in original['issues']),
            'previous_reference_categories':sorted(references[key]),
            'review_origin':'current_assistant', 'independent_human_review':'pending',
            'evidence_scope':'full_original_review',
        })
    return result


def run_semantic_review(data_dir=ROOT/'data'):
    annotations = json.loads((FOLDER/'annotations.json').read_text())
    sources = {r['source_row']:r for r in read_reviews(data_dir)}
    contexts=[row for row in annotations['cases'] if row.get('translation_context')]
    if contexts:
        specs=load_sources()['olist']['files']
        tables={}
        for name in ('olist_products_dataset.csv','olist_order_items_dataset.csv'):
            spec=specs[name]; path=data_dir/spec['destination']
            validate_file(path,spec)
            with path.open(encoding='utf-8-sig',newline='') as stream:
                tables[name]=list(csv.DictReader(stream))
        products={row['product_id']:row['product_category_name'] for row in tables['olist_products_dataset.csv']}
        order_products={(row['order_id'],row['product_id']) for row in tables['olist_order_items_dataset.csv']}
        for row in contexts:
            context=row['translation_context']
            if (products.get(context['product_id'])!=context['category']
                    or (sources[row['source_row']]['order_id'],context['product_id']) not in order_products):
                raise ValueError('辅助翻译语境不能与该评价关联')
    q4 = ROOT/'q4_llm_extraction'
    predictions = {r['source_row']:r for r in json.loads((q4/'extracted_issues.json').read_text())}
    references = {r['source_row']:set(r['categories']) for r in json.loads((q4/'evaluation_labels.json').read_text())['labels']}
    cases = compile_cases(annotations,sources,predictions,references)
    categories = Counter(issue['category'] for r in cases for issue in r['issues'])
    changes = [r for r in cases if {i['category'] for i in r['issues']} != set(r['previous_reference_categories'])]
    metrics = {
        'cases':len(cases), 'full_text_translations':len(cases),
        'issue_count':sum(categories.values()), 'categories':dict(categories),
        'cases_with_uncertainties':sum(bool(r['uncertainties']) for r in cases),
        'revised_prior_references':[r['source_row'] for r in changes],
        'authoring_stage_human_reviews':0, 'independent_accuracy':None,
        'numeric_confidence':'not assigned; no calibration evidence',
        'scope':'post-hoc analysis; cannot be used to claim unseen automatic accuracy',
    }
    content = json.dumps(cases,ensure_ascii=False,indent=2)+'\n'
    atomic_write_text(FOLDER/'cases.json',content)
    atomic_write_text(FOLDER/'analysis_metrics.json',json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
    doc = ['# Q4 复杂语义与完整翻译案例',
        f'当前助手逐条分析 {len(cases)} 条既有样本，并翻译完整原文。此处是事后草稿，不是独立人工验收，不改变冻结规则、extracted_issues.json 或原 60 条基准成绩。完整证据和翻译保存在 cases.json。',
        '## 怎样阅读',
        '先看原文与英文，再区分已报告的问题和补救请求；疑点保留在备注中。所有事件均为买家所述，不代表独立确认。没有赋予新的数值置信度。原文中的非标准拼写可在英文中按语境表达，但不得补造日期、型号、责任人或缺失尾句。',
        '## 参考标签的修订',
        '原参考标签也可能有偏差。本轮以下记录按更保守的证据口径修改，保留历史结果，不用新标签重新包装成旧版的测试真值：',
    ]
    for row in changes:
        doc.append(f"- {row['source_row']}：{', '.join(row['previous_reference_categories']) or '无'} → {', '.join(i['category'] for i in row['issues']) or '无'}。{row['analysis_zh']}")
    doc += ['## 原文、翻译和决策']
    for row in cases:
        doc += [f"### 源记录 {row['source_row']}", '原文（保留原始转义换行）：',
                '```text\n'+row['source_text']+'\n```', '完整英文：\n\n'+row['translation_en'],
                '问题：'+('; '.join(f"{i['category']} / {i['severity']}" for i in row['issues']) or '无充分证据支持具体问题'),
                '补救请求：'+(', '.join(row['requested_actions']) or '未明确提出'),
                f"情绪：{row['sentiment_label']}；卖家可跟进：{row['actionable_for_seller']}。", row['analysis_zh']]
        if row['uncertainties']:
            doc.append('待澄清：'+'；'.join(row['uncertainties']))
        if row['translation_context']:
            doc.append('辅助词义证据：关联商品类别为 `moveis_escritorio`（办公家具），词典支持凳子义；此上下文仅用于词义选择。[Priberam 词条](https://dicionario.priberam.org/mocho)。')
    doc += ['## 后续验收',
            '独立审核者应先在盲审包中按原文标注，再看完整译文检查否定、数量、型号、时间、请求与事实是否保留。review_campaign.py 生成两个独立填写包并检查完成度、分歧和翻译问题；没有真人提交时状态保持 pending，准确率为空。']
    atomic_write_text(FOLDER/'casebook.md','\n\n'.join(doc)+'\n')
    logging.getLogger(__name__).info('Q4 语义草稿完成：%s 条完整翻译；独立人工验收仍待完成',len(cases))
    return cases


if __name__ == '__main__':
    print(f'Compiled {len(run_semantic_review())} semantic review drafts')
