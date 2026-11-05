"""葡语投诉规则 v2：局部证据、否定/时间保护；不代替完整语言理解。"""

from dataclasses import dataclass
import re
import unicodedata

VERSION = "pt-rules-v2"
CATEGORIES = {"delivery_late", "wrong_product", "quality_defect", "missing_item", "seller_communication", "packaging", "other"}


@dataclass(frozen=True)
class Rule:
    category: str
    pattern: str
    english: str
    severity: str = "medium"
    guard: str = ""


# 英译对应匹配的短语，不把类别解释当成未出现的责任、原因或损失。
RULES = [
    Rule('delivery_late', r'(?:entrega|pedido|produto) (?:esta |veio |chegou |foi )?atrasad[oa]s?', 'The delivery/order/product is late.'),
    Rule('delivery_late', r'(?:muito |muita |grande )?(?:demora|atraso) (?:na|da|para a|para|pra) entrega(?:r)?', 'A delay in delivery.'),
    Rule('delivery_late', r'demorou(?: muito| demais| de mais| um pouco)? (?:para |pra |a )?(?:chegar|entregar|entrega|ser entregue)', 'It took a long time to arrive/be delivered.'),
    Rule('delivery_late', r'entrega (?:foi |e |muito )*(?:demorada|lenta)', 'Delivery was slow.'),
    Rule('delivery_late', r'(?:fora|depois|alem) do prazo', 'Outside/after the deadline.'),
    Rule('delivery_late', r'nao (?:foi entregue|recebi(?: o produto)?|receber(?: o produto)?|chegou) (?:dentro d[oae] |n[oae] )prazo', 'It was not delivered/received within the deadline.'),
    Rule('delivery_late', r'nao cumpri(?:u|ram|r) (?:com )?o prazo(?: de entrega)?', 'The deadline was not met.'),
    Rule('delivery_late', r'prazo(?: de entrega)?(?: do produto)? (?:ja )?(?:venceu|passou|expirou|esgotou|se esgotou)', 'The deadline has already passed.'),
    Rule('delivery_late', r'(?:estourou|passou|ultrapassou) (?:o |do )prazo(?: da entrega)?', 'The deadline was exceeded.'),
    Rule('delivery_late', r'prazo de entrega (?:e |foi |muito )*longo', 'The delivery lead time is long.'),
    Rule('delivery_late', r'(?:chegou|entregue) (?:com )?(?:\d+|um|dois|tres|quatro|cinco) dias? de atraso', 'It arrived/was delivered late by the stated number of days.'),
    Rule('delivery_late', r'era (?:pra|para) ser entregue[^.!?;\n]{0,35}e ate agora nada', 'It was due to be delivered, but so far nothing has arrived.'),
    Rule('missing_item', r'nao (?:recebi|recebemos)(?: (?:ainda )?(?:o |os |meu |minha |meus |minhas )?(?:produto|pedido|produtos|pedidos|mercadoria))?', 'I/we have not received it.', 'high', 'receipt'),
    Rule('missing_item', r'nunca recebi', 'I never received it.', 'high', 'receipt'),
    Rule('missing_item', r'nao (?:foi |foram |me )?(?:entregues?|entregou|entregaram|entregam|entregarem)', 'It was not delivered.', 'high', 'receipt'),
    Rule('missing_item', r'nao (?:chegou|chegaram)', 'It has not arrived.', 'high', 'receipt'),
    Rule('missing_item', r'produto(?:s)? incompleto(?:s)?', 'Incomplete product(s).', 'high'),
    Rule('missing_item', r'(?:pedido|entrega) parcial(?:mente)?', 'A partial order/delivery.', 'high'),
    Rule('missing_item', r'(?:ainda )?(?:estou |estamos )?aguardando (?:receber|a entrega|o produto|meu produto|o pedido)', 'I am still waiting to receive the delivery/product/order.', 'high', 'waiting'),
    Rule('missing_item', r'(?:ainda|ate agora) (?:estou )?aguardando', 'I am still waiting.', 'high', 'waiting'),
    Rule('missing_item', r'aguardando (?:a |o )?(?:terceira|segunda|outra|outro) (?:unidade|produto)', 'Waiting for the remaining unit/product.', 'high', 'waiting'),
    Rule('missing_item', r'quando (?:vcs |voces )?irao entregar', 'When will you deliver it?', 'high'),
    Rule('missing_item', r'entregaram (?:um|uma) so', 'They delivered only one.', 'high', 'partial'),
    Rule('missing_item', r'(?:faltou|faltaram|faltando|falta) (?:uma? |o |a |os |as )?(?:produto|item|peca|controle|acessorio|prendedor|tapete|encomenda)s?', 'A product/item/part/accessory is missing.', 'high', 'missing'),
    Rule('missing_item', r'(?:esta|estao|veio|vieram) faltando', 'Something is missing.', 'high', 'missing'),
    Rule('missing_item', r'nao veio (?:o|a|os|as|um|uma)\s+(?:produto|pedido|peca|controle|manual|acessorio|item)s?', 'The product/part/accessory did not come.', 'high'),
    Rule('missing_item', r'(?:so|apenas|somente) (?:recebi|veio|vieram|chegou|chegaram|enviaram|foi entregue) (?:apenas |somente )?(?:\d+|um|uma|dois|duas|tres)\b', 'Only the stated quantity was received/delivered.', 'high', 'partial'),
    Rule('missing_item', r'(?:recebi|veio|vieram|chegou|chegaram|entregaram|foi entregue) (?:so |apenas |somente )(?:\d+|um|uma|dois|duas|tres)\b', 'Only the stated quantity was received/delivered.', 'high', 'partial'),
    Rule('missing_item', r'entregaram (?:\d+|um|uma) dos (?:\d+|dois|tres|quatro) itens', 'Only part of the purchased items was delivered.', 'high'),
    Rule('wrong_product', r'(?:produto|produtos|modelo|cor|tamanho|medida|cartucho|pedido|entrega)(?:s)? (?:veio |vieram |esta |estao )?(?:errad[oa]s?|divergente)', 'Wrong product/model/colour/size/delivery.'),
    Rule('wrong_product', r'(?:veio|vieram|mandaram|enviaram|mandarao) errad[oa]s?', 'The wrong item was sent.'),
    Rule('wrong_product', r'(?:comprei|pedi) um(?:a)? (?:e )?veio outr[oa]', 'I ordered one thing and another arrived.'),
    Rule('wrong_product', r'diferente (?:do|da) (?:que (?:comprei|pedi)|anunciado|anuncio|foto|pedido|solicitado|escolhido)', 'Different from what was ordered/advertised.'),
    Rule('wrong_product', r'nao (?:e|foi) o (?:produto )?que (?:pedi|comprei|solicitei)', 'It is not what I ordered.'),
    Rule('wrong_product', r'nao (?:condiz|corresponde|confere) com (?:a|o|as|os) (?:foto|pedido|descricao|produto|imagem)s?', 'It does not match the picture/order/description.'),
    Rule('wrong_product', r'nao esta de acordo com as descricoes', 'It does not match the descriptions.'),
    Rule('wrong_product', r'(?:menor|inferior) (?:do|ao) (?:anunciado|que comprei)', 'Smaller/inferior to what was advertised/ordered.'),
    Rule('wrong_product', r'veio outro (?:tipo|modelo)', 'Another type/model arrived.'),
    Rule('quality_defect', r'(?:com|apresentou|apresenta|cheio de) defeitos?', 'With a defect/defects.', 'high', 'damage'),
    Rule('quality_defect', r'defeituos[oa]s?', 'Defective.', 'high', 'damage'),
    Rule('quality_defect', r'nao funciona(?:ram)?', 'It does not work.', 'high'),
    Rule('quality_defect', r'nao funcionou', 'It did not work.', 'high'),
    Rule('quality_defect', r'parou de funcionar', 'It stopped working.', 'high'),
    Rule('quality_defect', r'(?:quebrad[oa]s?|danificad[oa]s?|rachad[oa]s?|trincad[oa]s?|avariad[oa]s?)', 'Broken/damaged/cracked.', 'high', 'damage'),
    Rule('quality_defect', r'(?:arranhoes|aranhoes|arranhad[oa]s?|riscad[oa]s?|rasgad[oa]s?|amassad[oa]s?|manchad[oa]s?|descascando)', 'Scratched/torn/dented/stained/peeling.', 'medium', 'damage'),
    Rule('quality_defect', r'(?:pessima|baixa|ma|ruim|pesima) qualidade', 'Poor quality.'),
    Rule('quality_defect', r'qualidade (?:e |muito |bem )*(?:ruim|inferior|baixa|pessima)', 'The quality is poor/inferior.'),
    Rule('quality_defect', r'(?:mal|mau) acabament[oa]|mal acabado', 'Poor finish.'),
    Rule('quality_defect', r'nao (?:esta carregando|pega carga|carrega|liga)', 'It does not charge/turn on.', 'high'),
    Rule('quality_defect', r'(?:muito|bem) fin[oa]', 'Very thin.', 'medium', 'thin'),
    Rule('seller_communication', r'sem (?:resposta|retorno|comunicacao)', 'No response/communication.'),
    Rule('seller_communication', r'nao (?:me )?respond(?:e|em|eu|eram)', 'They do not/did not respond.'),
    Rule('seller_communication', r'nao (?:recebi|tive|obtive|tenho) (?:nenhuma? |uma? )?(?:resposta|retorno|respaldo|posicao)', 'I have received no response/support.'),
    Rule('seller_communication', r'(?:nao|nem) (?:me )?deram (?:resposta|retorno|satisfacao)', 'They did not give me a response.'),
    Rule('seller_communication', r'nao cons(?:egui|igo) (?:mais )?(?:entrar em )?(?:contato|contatar|falar|reclamar)', 'I cannot/could not make contact.'),
    Rule('seller_communication', r'ninguem (?:me )?(?:respondeu|responde|resolveu|resolve|retornou|retorna|da uma satisfacao)', 'Nobody responds/resolves it.'),
    Rule('seller_communication', r'nao tenho com quem falar', 'I have nobody to contact.'),
    Rule('seller_communication', r'(?:aguardando|aguardo|esperando) (?:o |um |uma )?(?:retorno|resposta|posicao)', 'Waiting for a response.'),
    Rule('seller_communication', r'nao fui (?:avisad[oa]|informad[oa])', 'I was not informed.'),
    Rule('seller_communication', r'deveria responder (?:aos|os) e-?mails?', 'They should answer customers\' emails.'),
    Rule('packaging', r'mal embalad[oa]s?', 'Poorly packaged.'),
    Rule('packaging', r'nao embalaram bem', 'They did not package it well.'),
    Rule('packaging', r'(?:embalagem|caixa) (?:do produto )?(?:original )?(?:(?:estava|veio|esta|toda|muito|totalmente) ){0,3}(?:rasgada|danificada|ruim|amassada|destruida|aberta|avariada)', 'The packaging/box was torn/damaged/poor/open.'),
    Rule('packaging', r'sem (?:a )?embalagem(?: original)?', 'Without (original) packaging.'),
    Rule('packaging', r'lacre violado', 'The seal was broken.'),
    Rule('packaging', r'embalagem deixou a desejar', 'The packaging was unsatisfactory.'),
    Rule('other', r'(?:sem|nao recebi a) nota fiscal', 'Without the invoice.'),
    Rule('other', r'frete (?:e |foi |muito )*caro', 'Shipping is expensive.'),
    Rule('other', r'(?:quero|solicito) (?:o )?reembolso', 'I want/request a refund.'),
    Rule('other', r'(?:quero|gostaria de ter) (?:o |meu )?dinheiro de volta', 'I want my money back.'),
    Rule('other', r'(?:quero|gostaria de) devolver', 'I want to return it.'),
    Rule('other', r'(?:falsificado|falsificacao|nao (?:e|parece(?: ser)?) original)', 'Alleged counterfeit / not (apparently) original.', 'medium', 'authenticity'),
    Rule('other', r'(?:nao (?:tem|tinha)|sem) estoque', 'Out of stock.'),
    Rule('other', r'demorou(?: muito)? (?:para |pra |a )?aprovar', 'Approval took a long time.'),

    Rule('delivery_late', r'(?:entrega|pedido|produto)(?: que| ja| esta| estava| foi){0,4} atrasad[oa]', 'The delivery/order is late.'),
    Rule('delivery_late', r'(?:ja )?passou a data limite', 'The deadline has passed.'),
    Rule('delivery_late', r'(?:depois|apos) (?:o|do) prazo', 'After the deadline.'),
    Rule('missing_item', r'(?:produto|pedido|pendente|mercadoria) nao veio', 'The product/order did not come.', 'high'),
    Rule('missing_item', r'sem (?:o |a )?(?:meu |minha )?(?:produto|pedido|mercadoria)', 'Without my product/order.', 'high'),
    Rule('missing_item', r'(?:nap|n[aã]o) recebi (?:o )?prodito', 'I have not received the product.', 'high'),
    Rule('quality_defect', r'(?:cabo|peca|botao) solt[oa]', 'A loose handle/part/button.'),
    Rule('quality_defect', r'(?:cortado|costurado) torto', 'Cut/sewn crooked.'),
    Rule('quality_defect', r'nao gostei da qualidade', 'I did not like the quality.'),
    Rule('quality_defect', r'qualidade (?:do produto )?nao foi a esperada', 'The quality was not as expected.'),
    Rule('quality_defect', r'nao (?:e |muito )?reforcad[oa]', 'Not very sturdy.'),
    Rule('quality_defect', r'(?:fragil|fragilidade)', 'Fragile.', 'medium', 'damage'),
    Rule('quality_defect', r'nao e apropriado', 'It is not suitable.'),
    Rule('seller_communication', r'(?:pessimo|ruim|mau|pesimo) atendimento', 'Poor customer service.'),
    Rule('seller_communication', r'nao (?:me )?retorna (?:o |os )?e-?mails?', 'They do not reply to emails.'),
    Rule('seller_communication', r'nao atende (?:o )?telefone', 'They do not answer the phone.'),
    Rule('seller_communication', r'nao (?:me )?foi respondido', 'I was not answered.'),
    Rule('seller_communication', r'nao disponibiliza (?:0800|telefone)', 'They do not provide a contact telephone number.'),
    Rule('seller_communication', r'nem (?:me )?foi respondido', 'I was not even answered.'),
    Rule('packaging', r'na (?:embalagem|caixa) nao consta (?:data de fabricacao|data de validade)', 'The packaging does not show the manufacturing/expiry date.'),
    Rule('wrong_product', r'nao confere para o modelo anunciado', 'It does not match the advertised model.'),
    Rule('wrong_product', r'(?:cor|modelo)(?: e o modelo)? alterad[oa]s?', 'The colour/model was changed.'),
    Rule('wrong_product', r'recebi (?:um|1) modelo que custa bem mais barato', 'I received a much cheaper model.'),
    Rule('other', r'preco (?:muito )?(?:caro|alto|exorbitante)', 'The price is excessively high.'),
    Rule('other', r'nao (?:me )?reembolsaram', 'They have not refunded me.'),
    Rule('other', r'nao recebi (?:o |meu |o meu )?(?:dinheiro|reembolso|estorno)', 'I have not received my money/refund.'),
    Rule('other', r'produto esta indisponivel', 'The product is unavailable.'),
    Rule('other', r'loja mal organizada', 'A poorly organised store.'),
    Rule('other', r'entregue na casa de um vizinho', 'Delivered to a neighbour\'s house.'),
]
COMPILED = [(rule, re.compile(r'\b(?:' + rule.pattern + r')\b')) for rule in RULES]
GENERIC_NEGATIVE = {
    'ruim':'Bad.', 'pessimo':'Terrible.', 'pessima':'Terrible.', 'muito ruim':'Very bad.',
    'nao gostei':'I did not like it.', 'nao recomendo':'I do not recommend it.',
    'horrivel':'Awful.', 'insatisfeito':'Dissatisfied.', 'insatisfeita':'Dissatisfied.',
    'decepcionado':'Disappointed.', 'decepcionada':'Disappointed.', 'razoavel':'Reasonable.',
    'regular':'Average.', 'deixou a desejar':'It fell short of expectations.',
}
POSITIVE = {'bom','boa','otimo','otima','excelente','gostei','muito bom','bom produto','produto bom',
            'muito boa','gostei do produto','recomendo','satisfeito','satisfeita','tudo em ordem',
            'tudo ok','ok','obrigada','obrigado','dentro das expectativas','entrega no prazo','uma loja boa'}


def fold_with_offsets(text):
    folded, offsets = [], []
    for index, char in enumerate(text):
        for normalized in unicodedata.normalize('NFD', char.lower()):
            if not unicodedata.combining(normalized):
                folded.append(normalized)
                offsets.append(index)
    return ''.join(folded), offsets


def clause_at(text, start, end):
    """供保护规则和人工复核使用，保留匹配前后的原句上下文。"""
    left=max(text.rfind(mark,0,start) for mark in '.!?;\n')+1
    candidates=[text.find(mark,end) for mark in '.!?;\n']
    right=min((p for p in candidates if p >= 0), default=len(text))
    return text[left:right].strip()


def blocked(rule, match, text):
    prefix=text[max(0,match.start()-55):match.start()]
    suffix=text[match.end():match.end()+80]
    clause=clause_at(text,match.start(),match.end())
    # 不从“没有损坏”“假如损坏”“差一点损坏”等陈述推出已发生的问题。
    if re.search(r'(?:sem|nenhum|nao|nunca|nao (?:e|esta|veio|chegou|tem|teve|apresenta|apresentou|foi|estava|ficou)(?: com)?)\s*$',prefix):
        return True
    if re.search(r'\b(?:se (?:vier|chegar|estiver|tiver)|poderia (?:vir|chegar|estar)|por pouco)\b[^.!?;]{0,30}$',prefix):
        return True
    if rule.category=='wrong_product' and re.search(r'\b(?:idealizar|imaginei|pensei|esperava)\b',clause):
        return True
    if rule.guard=='receipt':
        receipt_tail=re.sub(r'^\s+(?:(?:a|o|as|os|meu|minha|meus|minhas|uma?|nenhuma?|qualquer)\s+)*', '', suffix)
        if re.match(r'^(?:nota fiscal|resposta|retorno|contato|email|e-mail|satisfacao|estorno|reembolso|dinheiro|valor|codigo|informacao)\b',receipt_tail):
            return True
        if re.match(r'\s+(?:(?:a|o|um|uma|meu|minha|nenhuma?|qualquer)\s+)?(?:nota fiscal|resposta|retorno|contato|email|e-mail|satisfacao|estorno|reembolso|dinheiro|valor|codigo|informacao)',suffix):
            return True
        # “未按时收到”是延迟事实，不能单独推出现在仍未收到。
        if re.match(r'\s+(?:(?:o|meu) produto\s+)?(?:no prazo|dentro do prazo|na data|no dia|antes do prazo)',suffix):
            return True
        if re.search(r'\b(?:mas|porem|depois)\s+(?:(?:ja|agora|finalmente)\s+)?(?:recebi|chegou|foi entregue)\b',text[match.end():]):
            return True
    if rule.guard in {'waiting','missing'}:
        if re.search(r'\b(?:resposta|retorno|reembolso|estorno|troca|devolucao|coleta|vale)\b',clause):
            return True
        if re.search(r'\b(?:achando|achei|pensei|imaginei)\b',clause) and re.search(r'\b(?:recebi|recebido|dois dias separados)\b',text):
            return True
    if rule.guard=='partial':
        # “Só chegou um dia depois” não é quantidade faltante.
        if re.match(r'\s+(?:dia|dias|mes|meses|semana|semanas|hora|horas)\b',suffix):
            return True
        if not re.search(r'\b(?:comprei|comprad[oa]s?|pedido|pedi|falt|duas|dois|tres|quatro|kit|jogo|combo|unidades)\b|\d+',text):
            return True
    if rule.guard=='damage':
        # Dano na caixa não implica dano no produto.
        local_prefix=text[max(0,match.start()-35):match.start()]
        if re.search(r'\b(?:caixa|embalagem|pacote)\b[^,;.!?]*$',local_prefix):
            return True
    if rule.guard=='thin' and not re.search(r'\b(?:cobertor|manta|tecido|toalha|material)\b',text):
        return True
    return False


def translate_match(rule, phrase):
    """常见短语用对应的英译，避免枚举多个未出现的损坏类型。"""
    if rule.guard=='damage':
        if 'defeito' in phrase or phrase.startswith('defeituos'):
            return 'Defective.' if phrase.startswith('defeituos') else 'With a defect.'
        stems={'quebrad':'Broken.','danificad':'Damaged.','avariad':'Damaged.','rachad':'Cracked.','trincad':'Cracked.',
               'arranho':'Scratches.','aranho':'Scratches.','arranhad':'Scratched.','riscad':'Scratched.',
               'rasgad':'Torn.','amassad':'Dented.','manchad':'Stained.','descascando':'Peeling.'}
        return next((english for word,english in stems.items() if phrase.startswith(word)),rule.english)
    if rule.guard=='receipt':
        if 'recebemos' in phrase:
            return 'We have not received it.'
        if 'recebi' in phrase:
            return 'I have never received it.' if 'nunca' in phrase else 'I have not received it.'
        if 'cheg' in phrase:
            return 'It has not arrived.'
        if 'entregam' in phrase:
            return 'They do not deliver.'
        return 'It was not delivered.'
    if rule.category=='wrong_product' and ('errad' in phrase or 'divergente' in phrase):
        names={'produto':'product','produtos':'products','modelo':'model','cor':'colour','tamanho':'size',
               'medida':'size','cartucho':'cartridge','pedido':'order','entrega':'delivery'}
        subject=names.get(phrase.split()[0])
        return f'Wrong {subject}.' if subject else 'The wrong item was sent.'
    if rule.category=='packaging':
        if phrase.startswith(('embalagem','caixa')) and not 'desejar' in phrase:
            subject='box' if phrase.startswith('caixa') else 'packaging'
            words={'rasgada':'torn','danificada':'damaged','ruim':'poor','amassada':'dented','destruida':'destroyed','aberta':'open','avariada':'damaged'}
            adjective=next((en for pt,en in words.items() if pt in phrase),None)
            if adjective:
                return f'The {subject} was {adjective}.'
    if rule.guard=='authenticity':
        if 'parece' in phrase:
            return 'It does not appear to be original.'
        if 'nao' in phrase:
            return 'It is not original.'
        return 'Counterfeit.'  # 引述买家的说法，不能当成已核实事实。
    return rule.english


def extract_text(text):
    if not text.strip():
        return {'issues':[], 'sentiment_score':0.0, 'actionable_for_seller':False, 'confidence':0.0}, 'no_text', False
    folded, offsets=fold_with_offsets(text)
    short=re.sub(r'\s+',' ',re.sub(r'[^a-z0-9 ]','',folded)).strip()
    if short in POSITIVE:
        return {'issues':[], 'sentiment_score':0.6, 'actionable_for_seller':False, 'confidence':0.6}, 'positive_text_low_rating', True
    issues={}
    for rule,pattern in COMPILED:
        if rule.category in issues:
            continue
        for match in pattern.finditer(folded):
            if blocked(rule,match,folded):
                continue
            quote=text[offsets[match.start()]:offsets[match.end()-1]+1]
            issues[rule.category]={'category':rule.category,'severity':rule.severity,
                                  'evidence_quote':quote,'evidence_quote_en':translate_match(rule, match.group())}
            break
    if not issues:
        for negative,english in GENERIC_NEGATIVE.items():
            match=re.search(r'\b'+negative+r'\b',folded)
            if match and not re.search(r'\b(?:nao|nem)(?: e|foi|era|achei|considero|estava)?\s*$',folded[:match.start()]):
                quote=text[offsets[match.start()]:offsets[match.end()-1]+1]
                payload={'issues':[{'category':'other','severity':'low','evidence_quote':quote,'evidence_quote_en':english}],
                         'sentiment_score':-0.3 if negative in {'regular','razoavel'} else -0.8,
                         'actionable_for_seller':False,'confidence':0.5}
                return payload,'generic_sentiment',short!=negative
        return {'issues':[], 'sentiment_score':0.0, 'actionable_for_seller':False, 'confidence':0.0}, 'unresolved', True
    ordered=sorted(issues.values(),key=lambda i:i['category'])
    mixed=bool(re.search(r'\b(?:gostei|bom|boa|otimo|otima|excelente)\b',folded))
    complex_text=len(text)>120 or '?' in text or len(ordered)>2 or bool(re.search(r'\b(?:mas|porem|antes|depois|parece|acho)\b',folded))
    return {'issues':ordered,'sentiment_score':-0.3 if mixed else -0.7,
            'actionable_for_seller':True,'confidence':0.45 if complex_text else 0.65}, 'rule_evidence', complex_text
