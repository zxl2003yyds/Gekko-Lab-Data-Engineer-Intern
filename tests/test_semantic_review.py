"""检查来源、整段翻译和真正未填写的人工流程；所有审核者仅为测试夹具。"""
from copy import deepcopy
import hashlib
import json

import pytest

from q4_llm_extraction.build_semantic_review import compile_cases
from q4_llm_extraction import review_campaign as campaign


def semantic_fixture():
    source='Pedi CB436A e recebi CB435A.'
    sources={1:dict(source_row=1,review_id='r',order_id='o',review_comment_message=source)}
    annotations=dict(review_status='assistant_draft_pending_independent_human_review',cases=[dict(
        source_row=1,source_text_sha256=hashlib.sha256(source.encode()).hexdigest(),
        translation_en='I ordered CB436A and received CB435A.',protected_literals=['CB436A','CB435A'],
        issues=[dict(category='wrong_product',severity='medium')],sentiment_label='negative',
        actionable_for_seller=True,requested_actions=['exchange'],analysis_zh='型号不同',uncertainties=[])])
    predictions={1:dict(review_id='r',order_id='o',issues=[])}
    return annotations,sources,predictions,{1:set()}


def test_full_evidence_binding_and_no_mutation_of_frozen_predictions():
    args=semantic_fixture();before=deepcopy(args[2]);case=compile_cases(*args)[0]
    assert case['issues'][0]['evidence_quote']==args[1][1]['review_comment_message']
    assert case['issues'][0]['evidence_quote_en']==case['translation_en']
    assert args[2]==before and case['independent_human_review']=='pending'


@pytest.mark.parametrize('defect',['source','entity','empty_translation','duplicate_category'])
def test_bad_semantic_draft_is_not_published(defect):
    args=semantic_fixture();entry=args[0]['cases'][0]
    if defect=='source': args[1][1]['review_comment_message']+=' changed'
    if defect=='entity': entry['translation_en']=entry['translation_en'].replace('CB435A','CB436A')
    if defect=='empty_translation': entry['translation_en']=' '
    if defect=='duplicate_category': entry['issues']*=2
    with pytest.raises(ValueError): compile_cases(*args)


def create_campaign(tmp_path):
    # 无真实审核者参与；32 条虚构文本仅验证状态机。
    cases=[]
    for i in range(32):
        text=f'Synthetic case {i}.'
        cases.append(dict(source_row=i,source_text=text,source_text_sha256=hashlib.sha256(text.encode()).hexdigest(),translation_en=text,
                          issues=[],rule_categories=[],sentiment_label='positive',actionable_for_seller=False))
    folder=campaign.prepare_campaign(cases,tmp_path)
    campaign.seal_campaign(folder)
    return folder,cases


def fill_annotations(folder,reviewer='a',identity='synthetic test reviewer A'):
    path=folder/f'reviewer_{reviewer}_annotations.json'
    packet=json.loads(path.read_text())
    packet['attestation']=dict(reviewer_id=identity,is_human=True,independent_of_implementation=True,pt_en_capable=True)
    for row in packet['rows']:
        if row['primary_30']:
            row.update(issues=[],sentiment_label='positive',actionable_for_seller=False,notes='Synthetic test only')
    campaign.write_json(path,packet)
    return packet


def fill_translations(folder):
    path=campaign.prepare_translation(folder)
    packet=json.loads(path.read_text())
    for row in packet['rows']:
        row.update(verdict='faithful',error_types=[],notes='Synthetic test only')
    campaign.write_json(path,packet)
    return path


def test_blank_review_has_no_fake_human_metrics_and_translation_is_blocked(tmp_path):
    folder,_=create_campaign(tmp_path)
    status=campaign.assess(folder)
    assert status['status']=='awaiting_independent_human_review'
    assert status['independent_metrics'] is None and status['reviewed_cases']==0
    with pytest.raises(ValueError): campaign.prepare_translation(folder)
    packet=json.loads((folder/'reviewer_a_annotations.json').read_text())
    assert all('translation_en' not in r and r['issues'] is None for r in packet['rows'])


def test_rerun_preserves_written_annotations(tmp_path):
    folder,cases=create_campaign(tmp_path)
    fill_annotations(folder)
    before=(folder/'reviewer_a_annotations.json').read_bytes()
    campaign.prepare_campaign(cases,tmp_path)
    assert (folder/'reviewer_a_annotations.json').read_bytes()==before


def test_two_phase_review_accepts_only_reviewed_subset(tmp_path):
    folder,_=create_campaign(tmp_path)
    fill_annotations(folder)
    status=campaign.assess(folder)
    assert status['status']=='awaiting_translation_review'
    path=fill_translations(folder)
    status=campaign.assess(folder,translation_path=path)
    assert status['status']=='accepted_for_reviewed_sample'
    assert status['reviewed_cases']==30 and status['unreviewed_cases']==2
    assert status['independent_metrics']['assistant_drafts']['exact']==30


def test_changed_annotations_invalidate_translation_snapshot(tmp_path):
    folder,_=create_campaign(tmp_path)
    packet=fill_annotations(folder);path=fill_translations(folder)
    packet['rows'][0]['notes']='Updated after translation was prepared'
    campaign.write_json(folder/'reviewer_a_annotations.json',packet)
    status=campaign.assess(folder,translation_path=path)
    assert status['independent_metrics'] is None
    assert '封存' in status['reason']


def test_translation_error_requires_a_real_revision_and_blocks_acceptance(tmp_path):
    folder,_=create_campaign(tmp_path)
    fill_annotations(folder);path=fill_translations(folder)
    packet=json.loads(path.read_text());packet['rows'][0].update(verdict='major_error',error_types=['negation'],corrected_translation='Synthetic corrected translation.')
    campaign.write_json(path,packet)
    result=campaign.assess(folder,translation_path=path)
    assert result['status']=='changes_required'
    assert result['language_review_counts']['major_error']==1


def test_second_reviewer_must_be_distinct_and_disagreements_are_visible(tmp_path):
    folder,_=create_campaign(tmp_path)
    fill_annotations(folder);path=fill_translations(folder)
    fill_annotations(folder,'b')
    with pytest.raises(ValueError):
        campaign.assess(folder,translation_path=path,second_annotations=folder/'reviewer_b_annotations.json')
    packet=fill_annotations(folder,'b','synthetic test reviewer B')
    selected=next(row for row in packet['rows'] if row['issues'] is not None)
    selected['sentiment_label']='mixed'
    campaign.write_json(folder/'reviewer_b_annotations.json',packet)
    result=campaign.assess(folder,translation_path=path,second_annotations=folder/'reviewer_b_annotations.json')
    assert result['status']=='requires_human_adjudication'
    assert len(result['second_review']['conflict_task_ids'])==1


def test_manifest_threshold_cannot_be_lowered_to_report_empty_success(tmp_path):
    folder,_=create_campaign(tmp_path)
    path=folder/'manifest.json';manifest=json.loads(path.read_text());manifest['minimum_reviewed']=0
    campaign.write_json(path,manifest)
    with pytest.raises(ValueError):campaign.load_campaign(folder)


def test_selected_cases_cannot_be_swapped_for_easier_ones(tmp_path):
    folder,_=create_campaign(tmp_path)
    packet=fill_annotations(folder)
    primary=next(row for row in packet['rows'] if row['primary_30'])
    replacement=next(row for row in packet['rows'] if not row['primary_30'])
    primary['issues']=None
    replacement.update(issues=[],sentiment_label='positive',actionable_for_seller=False)
    campaign.write_json(folder/'reviewer_a_annotations.json',packet)
    with pytest.raises(ValueError,match='primary_30'):
        campaign.prepare_translation(folder)
    assert campaign.assess(folder)['independent_metrics'] is None


def test_unfilled_second_review_is_not_reported_as_agreement(tmp_path):
    folder,_=create_campaign(tmp_path)
    fill_annotations(folder);path=fill_translations(folder)
    packet=fill_annotations(folder,'b','synthetic test reviewer B')
    for row in packet['rows']:
        row['issues']=None
    campaign.write_json(folder/'reviewer_b_annotations.json',packet)
    with pytest.raises(ValueError,match='primary_30'):
        campaign.assess(folder,translation_path=path,second_annotations=folder/'reviewer_b_annotations.json')
