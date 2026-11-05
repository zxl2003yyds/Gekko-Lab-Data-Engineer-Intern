"""验证持久化失败、快照串版和畸形记录不能悄悄通过。"""
from copy import deepcopy
import hashlib
import json

import pytest

from q4_llm_extraction import io_utils
from q4_llm_extraction.evaluate import score_labels, validate_snapshot
from q4_llm_extraction.extract_reviews import validate_record
from q4_llm_extraction.rules import VERSION


def valid_record():
    source=dict(review_id='r',order_id='o',source_row=1,review_comment_message='Chegou quebrado.')
    result=dict(review_id='r',order_id='o',source_row=1,issues=[dict(category='quality_defect',severity='high',evidence_quote='quebrado',evidence_quote_en='Broken.')],sentiment_score=-0.7,confidence=0.65,actionable_for_seller=True,needs_review=False)
    return result,source


@pytest.mark.parametrize('key,value', [('confidence',True),('confidence',float('nan')),('sentiment_score',float('inf')),('needs_review','yes'),('review_id','wrong'),('order_id','other'),('source_row',2),('issues',None)])
def test_invalid_record_rejected(key,value):
    record,source=valid_record()
    record[key]=value
    with pytest.raises(ValueError):
        validate_record(record,source)


def test_quoted_evidence_and_duplicate_categories_rejected():
    record,source=valid_record()
    validate_record(record,source)
    changed=deepcopy(record)
    changed['issues'][0]['evidence_quote']='invented quote'
    with pytest.raises(ValueError):
        validate_record(changed,source)
    changed=deepcopy(record)
    changed['issues'] *= 2
    with pytest.raises(ValueError):
        validate_record(changed,source)


def test_failed_replace_preserves_previous_output_and_cleans_temporary_file(monkeypatch,tmp_path):
    target=tmp_path/'result.json'; target.write_text('old result')
    def fail(*args):
        raise OSError('simulated full disk during publication')
    monkeypatch.setattr(io_utils.os,'replace',fail)
    with pytest.raises(OSError):
        io_utils.atomic_write_text(target,'new result')
    assert target.read_text()=='old result'
    assert list(tmp_path.iterdir())==[target]


def test_scoring_keeps_false_positives_and_false_negatives_separate():
    score=score_labels({1:{'missing_item'},2:{'wrong_product'},3:set()}, {1:{'missing_item'},2:set(),3:{'other'}})
    assert (score['tp'],score['fp'],score['fn'],score['exact'])==(1,1,1,1)
    assert score['precision']==score['recall']==0.5
    empty=score_labels({1:set()},{1:set()})
    assert empty['precision'] is None and empty['recall'] is None
    with pytest.raises(ValueError):
        score_labels({1:set()}, {})


def test_torn_output_or_changed_frozen_rules_rejected():
    content=b'[]'; rules=b'frozen'
    manifest=dict(version=VERSION, output_sha256=hashlib.sha256(content).hexdigest())
    design=dict(frozen_rule_sha256=hashlib.sha256(rules).hexdigest())
    validate_snapshot(content,manifest,design,rules)
    with pytest.raises(ValueError):
        validate_snapshot(content+b' ',manifest,design,rules)
    with pytest.raises(ValueError):
        validate_snapshot(content,manifest,design,b'changed')


def test_evaluation_rerun_preserves_legacy_review_notes(tmp_path, monkeypatch):
    from q4_llm_extraction import evaluate
    folder = tmp_path / 'q4_llm_extraction'
    audit = tmp_path / '.local/q4'
    folder.mkdir()
    audit.mkdir(parents=True)
    content = json.dumps([dict(source_row=1, review_id='synthetic', issues=[])]).encode()
    (folder / 'extracted_issues.json').write_bytes(content)
    (folder / 'rules.py').write_bytes(b'synthetic frozen rules')
    (folder / 'evaluation_design.json').write_text(json.dumps(dict(
        frozen_rule_sha256=hashlib.sha256(b'synthetic frozen rules').hexdigest(),
        development_text_sha256=[], sampling_unit='unique_nonempty_text')))
    (folder / 'evaluation_labels.json').write_text(json.dumps(dict(
        reviewer='synthetic fixture only', labels=[dict(source_row=1, categories=[], note='synthetic')])) )
    (audit / 'evaluation_holdout.json').write_text(json.dumps([dict(source_row=1, text='bom')]))
    (audit / 'metrics.json').write_text(json.dumps(dict(
        version=VERSION, output_sha256=hashlib.sha256(content).hexdigest(), rows=1, needs_review=0)))
    saved = b'[{"notes": "synthetic saved review - do not erase"}]'
    target = audit / 'manual_review_template.json'
    target.write_bytes(saved)
    monkeypatch.setattr(evaluate, 'ROOT', tmp_path)
    evaluate.evaluate()
    assert target.read_bytes() == saved
