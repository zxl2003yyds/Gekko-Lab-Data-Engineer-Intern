"""本地双阶段人工复核：先原文盲标，再审译文；不会代填人工身份或验收。"""
import argparse
import hashlib
import json
from pathlib import Path
import random

from download_data import ROOT
from q4_llm_extraction.evaluate import score_labels
from q4_llm_extraction.io_utils import atomic_write_text
from q4_llm_extraction.rules import CATEGORIES


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def write_json(path,value):
    atomic_write_text(path,json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def attestation():
    return {'reviewer_id':None,'is_human':None,'independent_of_implementation':None,'pt_en_capable':None}


def prepare_campaign(cases, output_root):
    """相同快照复用目录，永不覆盖已填写的人工文件。"""
    case_hash=sha(sorted(cases,key=lambda row:row['source_row']))
    campaign_id=case_hash[:16]
    folder=Path(output_root)/campaign_id
    folder.mkdir(parents=True,exist_ok=True)
    ordered=list(cases)
    random.Random(271828).shuffle(ordered)
    tasks=[{'task_id':hashlib.sha256((campaign_id+':'+str(row['source_row'])).encode()).hexdigest()[:16],
            'text':row['source_text'],'source_sha256':row['source_text_sha256'],
            'primary_30':index<30} for index,row in enumerate(ordered)]
    manifest={'schema_version':1,'campaign_id':campaign_id,'snapshot_sha256':case_hash,'tasks':tasks,
              'minimum_reviewed':30,'scope':'post-hoc sample audit, not unseen generalisation'}
    snapshot={task['task_id']:row for task,row in zip(tasks,ordered,strict=True)}
    manifest_path=folder/'manifest.json'
    if manifest_path.exists():
        if json.loads(manifest_path.read_text())!=manifest:
            raise ValueError('已有复核活动清单变化，拒绝覆盖')
        if sha(list(json.loads((folder/'coordinator_snapshot.json').read_text()).values()))!=sha(ordered):
            raise ValueError('已有复核快照变化')
    else:
        write_json(manifest_path,manifest)
        write_json(folder/'coordinator_snapshot.json',snapshot)
    for reviewer in ('a','b'):
        path=folder/f'reviewer_{reviewer}_annotations.json'
        if not path.exists():
            write_json(path,{'campaign_id':campaign_id,'attestation':attestation(),
                'instructions':'先仅按原文填写 primary_30（建议全 60 条）。不要先看译文、自动预测或助手参考答案。未审核项保持 issues=null；审核后无问题填 []。B 为可选第二审核者，不可复制 A。',
                'rows':[{**task,'issues':None,'sentiment_label':None,'actionable_for_seller':None,'notes':None} for task in tasks]})
    return folder


def load_campaign(folder):
    folder=Path(folder)
    manifest=json.loads((folder/'manifest.json').read_text())
    snapshot=json.loads((folder/'coordinator_snapshot.json').read_text())
    content_hash=sha(sorted(snapshot.values(),key=lambda row:row['source_row']))
    if (manifest.get('minimum_reviewed')!=30 or manifest.get('snapshot_sha256')!=content_hash
            or manifest.get('campaign_id')!=content_hash[:16]):
        raise ValueError('复核活动阈值、版本或快照摘要发生变化')
    # 原案例顺序与随机分发顺序不同，按来源号比较内容签名以外，再校验每条来源。
    if set(snapshot)!={r['task_id'] for r in manifest['tasks']}:
        raise ValueError('任务与冻结案例快照不一致')
    for task in manifest['tasks']:
        case=snapshot[task['task_id']]
        if hashlib.sha256(task['text'].encode()).hexdigest()!=task['source_sha256'] or case['source_text']!=task['text']:
            raise ValueError('复核原文与快照不一致')
    # 对照按 source_row 排序的哈希可验证快照内容，额外封存字段如下。
    sealed=folder/'snapshot_seal.json'
    if not sealed.exists():
        raise ValueError('缺少已封存的快照摘要')
    if json.loads(sealed.read_text())['sha256']!=sha(snapshot):
        raise ValueError('协调者快照在封存后被修改')
    return manifest,snapshot


def seal_campaign(folder):
    path=Path(folder)/'snapshot_seal.json'
    snapshot=json.loads((Path(folder)/'coordinator_snapshot.json').read_text())
    expected={'sha256':sha(snapshot)}
    if path.exists():
        if json.loads(path.read_text())!=expected:
            raise ValueError('现有快照摘要不一致')
    else:
        write_json(path,expected)


def validate_attestation(value):
    reviewer=value.get('reviewer_id')
    if not isinstance(reviewer,str) or not reviewer.strip():
        raise ValueError('待真实审核者填写 reviewer_id')
    if any(value.get(key) is not True for key in ('is_human','independent_of_implementation','pt_en_capable')):
        raise ValueError('须由人工如实声明其独立性和葡英审核能力')
    return reviewer.strip()


def validate_annotations(packet, manifest):
    if packet.get('campaign_id')!=manifest['campaign_id']:
        raise ValueError('标注属于其他复核活动')
    reviewer=validate_attestation(packet.get('attestation',{}))
    tasks={r['task_id']:r for r in manifest['tasks']}
    rows=packet.get('rows',[])
    if len(rows)!=len(tasks) or {r.get('task_id') for r in rows}!=set(tasks):
        raise ValueError('标注任务缺失、重复或新增')
    answers={}
    for row in rows:
        key=row['task_id']; task=tasks[key]
        if row.get('text')!=task['text'] or row.get('source_sha256')!=task['source_sha256']:
            raise ValueError('审核包原文被更改')
        if row.get('issues') is None:
            continue
        if not isinstance(row['issues'],list):
            raise ValueError('issues 必须是列表，未知/未审是 null')
        categories=set()
        for item in row['issues']:
            if set(item)!={'category','severity','evidence_quote'}:
                raise ValueError('人工问题项须填写 category、severity、evidence_quote')
            if item['category'] not in CATEGORIES or item['category'] in categories or item['severity'] not in {'low','medium','high'}:
                raise ValueError('人工标注类别/严重程度无效')
            categories.add(item['category'])
            quote=item['evidence_quote']
            if not isinstance(quote,str) or not quote.strip() or quote not in task['text']:
                raise ValueError('人工证据必须来自原文')
        if row.get('sentiment_label') not in {'positive','negative','mixed','unknown'} or type(row.get('actionable_for_seller')) is not bool:
            raise ValueError('请完成已审记录的情绪和可行动性')
        answers[key]=row
    return reviewer,answers


def require_review_scope(answers, manifest):
    """必须覆盖预先选定的共同样本，不能以容易样本替换。"""
    required={row['task_id'] for row in manifest['tasks'] if row['primary_30']}
    if len(required)!=manifest['minimum_reviewed'] or not required<=set(answers):
        raise ValueError('须完成预先指定的全部 30 条 primary_30 样本，不可自行替换')


def prepare_translation(folder, reviewer='a'):
    folder=Path(folder);manifest,snapshot=load_campaign(folder)
    annotations=json.loads((folder/f'reviewer_{reviewer}_annotations.json').read_text())
    identity,answers=validate_annotations(annotations,manifest)
    require_review_scope(answers,manifest)
    sealed_hash=sha(annotations)
    name=f'reviewer_{reviewer}_translations_{sealed_hash[:12]}.json'
    output=folder/name
    if not output.exists():
        write_json(folder/f'reviewer_{reviewer}_sealed_annotations_{sealed_hash[:12]}.json',annotations)
        write_json(output,{'campaign_id':manifest['campaign_id'],'reviewer_id':identity,'annotations_sha256':sealed_hash,
            'instructions':'此阶段才看助手译文。verdict 填 faithful/minor_error/major_error；error_types 填数组（无错误 []）。有错误时填写 corrected_translation。不要回写第一阶段原标注；分歧单独讨论并保留版本。',
            'rows':[{'task_id':key,'source_text':snapshot[key]['source_text'],
                     'translation_en':snapshot[key]['translation_en'], 'translation_context':snapshot[key].get('translation_context'),
                     'verdict':None,'error_types':None,'corrected_translation':None,'notes':None} for key in answers]})
    return output


def validate_translation(packet,annotations,answers,manifest,snapshot):
    if packet.get('campaign_id')!=manifest['campaign_id'] or packet.get('annotations_sha256')!=sha(annotations):
        raise ValueError('译文审核与已封存的第一阶段标注不一致')
    if packet.get('reviewer_id')!=annotations['attestation']['reviewer_id'].strip():
        raise ValueError('两个阶段须为同一审核者')
    rows=packet.get('rows',[])
    if len(rows)!=len(answers) or {r.get('task_id') for r in rows}!=set(answers):
        raise ValueError('译文审核未覆盖全部已标注记录')
    allowed={'negation','time','quantity','entity','subject','modality','omission','addition','word_choice','grammar'}
    for row in rows:
        source=snapshot[row['task_id']]
        if row.get('source_text')!=source['source_text'] or row.get('translation_en')!=source['translation_en']:
            raise ValueError('待审原文/译文被替换，请另填 corrected_translation')
        verdict=row.get('verdict');errors=row.get('error_types')
        if verdict not in {'faithful','minor_error','major_error'} or not isinstance(errors,list) or not set(errors)<=allowed:
            raise ValueError('译文审核尚未完成或错误类型非法')
        if verdict=='faithful' and errors:
            raise ValueError('faithful 不应同时报告错误')
        if verdict!='faithful' and (not errors or not isinstance(row.get('corrected_translation'),str) or not row['corrected_translation'].strip()):
            raise ValueError('发现翻译错误时须给出错误类型和修订译文')
    return rows


def assess(folder,reviewer='a',translation_path=None,second_annotations=None):
    folder=Path(folder);manifest,snapshot=load_campaign(folder)
    packet=json.loads((folder/f'reviewer_{reviewer}_annotations.json').read_text())
    report={'campaign_id':manifest['campaign_id'],'status':'awaiting_independent_human_review',
            'reviewed_cases':0,'total_cases':len(snapshot),'independent_metrics':None,
            'identity_limit':'程序只能校验审核者声明和文件一致性，不能验证其真实身份、语言能力或是否偷看答案。',
            'scope':'已见样本的人工核验，不是未见数据泛化能力。'}
    try:
        identity,answers=validate_annotations(packet,manifest)
        report.update(reviewer_id=identity,reviewed_cases=len(answers))
        require_review_scope(answers,manifest)
        report['status']='awaiting_translation_review'
        if translation_path is None:
            report['reason']='先运行 prepare-translation，再由同一人工填写译文审核。'
            write_json(folder/f'reviewer_{reviewer}_status.json',report)
            return report
        translated=validate_translation(json.loads(Path(translation_path).read_text()),packet,answers,manifest,snapshot)
    except (ValueError,KeyError,TypeError) as exc:
        report['reason']=str(exc)
        write_json(folder/f'reviewer_{reviewer}_status.json',report)
        return report
    expected={key:{i['category'] for i in value['issues']} for key,value in answers.items()}
    proposed={key:{i['category'] for i in snapshot[key]['issues']} for key in answers}
    frozen={key:set(snapshot[key]['rule_categories']) for key in answers}
    differences=[]
    for key,value in answers.items():
        issue_signature=lambda items: sorted((i['category'],i['severity']) for i in items)
        draft=snapshot[key]
        if (issue_signature(value['issues'])!=issue_signature(draft['issues'])
                or value['sentiment_label']!=draft['sentiment_label']
                or value['actionable_for_seller']!=draft['actionable_for_seller']):
            differences.append(key)
    errors=[r['task_id'] for r in translated if r['verdict']!='faithful']
    report.update(status='changes_required' if differences or errors else 'accepted_for_reviewed_sample',
        independent_metrics={'assistant_drafts':score_labels(expected,proposed),'frozen_rules':score_labels(expected,frozen)},
        semantic_difference_task_ids=differences,translation_error_task_ids=errors,
        unreviewed_cases=len(snapshot)-len(answers),language_review_counts={key:sum(r['verdict']==key for r in translated) for key in ('faithful','minor_error','major_error')})
    if second_annotations:
        second=json.loads(Path(second_annotations).read_text())
        other,other_answers=validate_annotations(second,manifest)
        if other==identity:
            raise ValueError('第二审核者不能与第一审核者相同')
        require_review_scope(other_answers,manifest)
        shared=set(answers)&set(other_answers)
        def signature(row):
            return sorted((i['category'],i['severity']) for i in row['issues']),row['sentiment_label'],row['actionable_for_seller']
        conflicts=sorted(key for key in shared if signature(answers[key])!=signature(other_answers[key]))
        report['second_review']={'reviewer_id':other,'shared_cases':len(shared),'conflict_task_ids':conflicts}
        if conflicts:
            report['status']='requires_human_adjudication'
    write_json(folder/f'reviewer_{reviewer}_status.json',report)
    return report


def prepare_default_campaign(cases):
    folder=prepare_campaign(cases,ROOT/'.local/q4/human_review')
    seal_campaign(folder)
    status=folder/'reviewer_a_status.json'
    # 重跑流水线保留已有人工结果；需要重新计算时显式运行 assess。
    if not status.exists():
        assess(folder)
    return folder


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','prepare-translation','assess'])
    parser.add_argument('--campaign',type=Path)
    parser.add_argument('--reviewer',choices=['a','b'],default='a')
    parser.add_argument('--translation',type=Path)
    parser.add_argument('--second-annotations',type=Path)
    args=parser.parse_args()
    if args.command=='prepare':
        cases=json.loads((ROOT/'q4_llm_extraction/semantic_review/cases.json').read_text())
        folder=prepare_default_campaign(cases)
        print(folder)
        print((folder/'reviewer_a_status.json').read_text())
    elif args.campaign is None:
        parser.error('需要 --campaign 路径')
    elif args.command=='prepare-translation':
        print(prepare_translation(args.campaign,args.reviewer))
    else:
        print(json.dumps(assess(args.campaign,args.reviewer,args.translation,args.second_annotations),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
