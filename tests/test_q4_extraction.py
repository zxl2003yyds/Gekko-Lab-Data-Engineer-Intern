"""检查证据、保守分流和与开发缓存无关的可复现性。"""
import json

import pytest

from download_data import ROOT
from q4_llm_extraction import extract_reviews as extraction
from q4_llm_extraction.rules import extract_text


@pytest.mark.parametrize('value,status,review', [('', 'no_text', False), (' \n ', 'no_text', False), ('bom','positive_text_low_rating',True), ('Não sei avaliar','unresolved',True)])
def test_empty_positive_and_unknown_are_distinguished(value, status, review):
    payload, route, pending = extract_text(value)
    assert payload['issues'] == []
    assert (route,pending) == (status,review)


@pytest.mark.parametrize('value,expected', [
    ('NÃO RECEBI o produto.', {'missing_item'}),
    ('Não recebi resposta.', {'seller_communication'}),
    ('Não recebi a nota fiscal.', {'other'}),
    ('Chegou com defeito, mal embalado.', {'quality_defect','packaging'}),
    ('Não veio com defeito.', set()),
    ('Demorou muito para aprovar.', {'other'}),
])
def test_evidence_and_important_false_positive_guards(value, expected):
    payload, _, _ = extract_text(value)
    assert {i['category'] for i in payload['issues']} == expected
    for issue in payload['issues']:
        assert issue['evidence_quote'] in value


def test_batch_keeps_duplicate_review_ids_and_is_deterministic_without_dev_cache(monkeypatch,tmp_path):
    output = tmp_path/'q4_llm_extraction'
    output.mkdir()
    (output/'evaluation_design.json').write_text(json.dumps(dict(development_source_rows=[1],holdout_seed=202603,holdout_size=2)))
    rows = [dict(source_row=i,review_id='duplicate',order_id=str(i),review_score='1',review_comment_message=t) for i,t in enumerate(['Ruim','Não recebi o produto','Não recebi o produto'],1)]
    monkeypatch.setattr(extraction,'ROOT',tmp_path)
    monkeypatch.setattr(extraction,'OUTPUT',output)
    monkeypatch.setattr(extraction,'read_reviews',lambda _: rows)
    one=extraction.run_extraction(tmp_path)
    sample=json.loads((tmp_path/'.local/q4/evaluation_holdout.json').read_text())
    assert {r['source_row'] for r in sample} == {2,3}
    # 任意过时的开发缓存不应改变版本化样本。
    (tmp_path/'.local/q4/evaluation_sample.json').write_text('[{"source_row":2}]')
    two=extraction.run_extraction(tmp_path)
    assert one['output_sha256'] == two['output_sha256']
    assert json.loads((tmp_path/'.local/q4/evaluation_holdout.json').read_text()) == sample
    records=json.loads((output/'extracted_issues.json').read_text())
    assert len(records)==3 and {r['source_row'] for r in records}=={1,2,3}
    assert one['unique_exact_texts']==2 and one['api_calls']==0


@pytest.mark.skipif(not (ROOT/'data/olist/olist_order_reviews_dataset.csv').exists(), reason='需先准备固定版本 Olist 文件')
def test_committed_reference_labels_match_reproducible_holdout():
    rows = extraction.read_reviews(ROOT/'data')
    selected = {r['source_row'] for r in extraction.holdout_sample(rows)}
    labels=json.loads((ROOT/'q4_llm_extraction/evaluation_labels.json').read_text())['labels']
    assert selected == {r['source_row'] for r in labels}


@pytest.mark.parametrize('value,expected', [
    ('Não recebi o meu dinheiro.', {'other'}),
    ('Não recebi no prazo, mas depois chegou.', {'delivery_late'}),
    ('Se vier com defeito, devolvo.', set()),
    ('Por pouco não foi danificado.', set()),
    ('O produto não é ruim.', set()),
    ('Não veio errado.', set()),
    ('A caixa do produto veio avariada.', {'packaging'}),
    ('Comprei duas capas e recebi apenas uma.', {'missing_item'}),
    ('Comprei uma capa e recebi uma capa.', set()),
    ('Só chegou um dia depois.', set()),
    ('Não obtive nenhuma resposta.', {'seller_communication'}),
    ('Muito bom, mas chegou quebrado.', {'quality_defect'}),
])
def test_v2_context_and_negation_regressions(value, expected):
    payload, _, _ = extract_text(value)
    assert {issue['category'] for issue in payload['issues']} == expected


def test_literal_damage_translation_and_mixed_sentiment():
    result, _, review = extract_text('Muito bom, mas chegou quebrado.')
    assert result['issues'][0]['evidence_quote_en'] == 'Broken.'
    assert result['sentiment_score'] == -0.3 and review


def test_all_contexts_retained_for_repeated_quote():
    text = 'Não veio quebrado. O outro veio quebrado.'
    contexts = extraction.evidence_contexts(text, [{'category':'quality_defect','evidence_quote':'quebrado'}])
    assert contexts['quality_defect'] == ['Não veio quebrado', 'O outro veio quebrado']


def test_unique_nonempty_holdout_excludes_training_text_duplicates(monkeypatch,tmp_path):
    import hashlib
    monkeypatch.setattr(extraction,'OUTPUT',tmp_path)
    design = dict(development_source_rows=[1], development_text_sha256=[hashlib.sha256(b'train').hexdigest()], sampling_unit='unique_nonempty_text', holdout_seed=1, holdout_size=2)
    (tmp_path/'evaluation_design.json').write_text(json.dumps(design))
    rows=[dict(source_row=i,review_comment_message=t) for i,t in enumerate(['train','train','','a','a','b'],1)]
    assert {r['review_comment_message'] for r in extraction.holdout_sample(rows)} == {'a','b'}
