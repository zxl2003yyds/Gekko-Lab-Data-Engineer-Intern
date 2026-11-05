"""从葡萄牙语明确短语抽取证据；规则版本固定，置信度不是校准概率。"""

import re
import unicodedata

VERSION = "pt-rules-v1"
CATEGORIES = {"delivery_late", "wrong_product", "quality_defect", "missing_item", "seller_communication", "packaging", "other"}
# 正则作用于去重音小写副本，证据通过位置映射从原文截取。
RULES = [
    ("delivery_late", r"(?:entrega|produto|pedido) atrasad[oa]s?", "The delivery, product or order is late.", "medium"),
    ("delivery_late", r"atraso na entrega", "Delay in delivery.", "medium"),
    ("delivery_late", r"fora do prazo", "Outside the agreed timeframe.", "medium"),
    ("delivery_late", r"nao cumpriu o prazo(?: de entrega)?", "The agreed delivery deadline was not met.", "medium"),
    ("delivery_late", r"demorou (?:muito|demais|de mais)(?: (?:para |pra )?entregar| (?:na |a )?entrega)", "Delivery took too long.", "medium"),
    ("delivery_late", r"prazo (?:maximo )?(?:ja )?(?:se )?esgotou", "The deadline has already expired.", "medium"),
    ("missing_item", r"nao (?:recebi|recebemos)(?: (?:ainda )?(?:o|os|meu|minha|meus|minhas) (?:produto|pedido|produtos|pedidos))?", "I/we have not received it.", "high"),
    ("missing_item", r"nao (?:(?:foi |foram )?entregues?|entregaram)", "It was not delivered.", "high"),
    ("missing_item", r"nao (?:me )?entregou", "It was not delivered to me.", "high"),
    ("missing_item", r"nao chegou", "It has not arrived.", "high"),
    ("missing_item", r"(?:pedido|entrega) parcial(?:mente)?", "The order/delivery was only partial.", "high"),
    ("missing_item", r"recebi o pedido parcialmente", "I received only part of the order.", "high"),
    ("missing_item", r"faltou (?:uma? |o |a )?(?:produto|item|peca|controle|acessorio)s?", "A product, item, part or accessory was missing.", "high"),
    ("wrong_product", r"produto errado", "Wrong product.", "high"),
    ("wrong_product", r"(?:produto |cor |tamanho )?diferente (?:do|da) (?:anunciado|anuncio|foto|pedido|solicitado|escolhido)", "Different from what was advertised, pictured or ordered.", "medium"),
    ("wrong_product", r"nao condiz com a foto", "It does not match the photo.", "medium"),
    ("quality_defect", r"(?:com |apresentou )defeito", "The product has a defect.", "high"),
    ("quality_defect", r"nao funciona(?:ram)?", "It does not work.", "high"),
    ("quality_defect", r"nao funcionou", "It did not work.", "high"),
    ("quality_defect", r"(?:veio |chegou )quebrad[oa]", "It arrived broken.", "high"),
    ("quality_defect", r"(?:veio |chegou )danificad[oa]", "It arrived damaged.", "high"),
    ("quality_defect", r"mal acabado", "Poorly finished.", "medium"),
    ("quality_defect", r"(?:pessima|baixa) qualidade", "Very poor quality.", "medium"),
    ("quality_defect", r"nao (?:esta carregando|pega carga)", "It does not charge.", "high"),
    ("seller_communication", r"sem resposta", "No response.", "medium"),
    ("seller_communication", r"nao respond(?:e|em|eu|eram)", "They do not/did not respond.", "medium"),
    ("seller_communication", r"(?:nao|nem) (?:tive|obtive) (?:resposta|retorno)", "I did not receive a response.", "medium"),
    ("seller_communication", r"nao consegui contato", "I could not make contact.", "medium"),
    ("seller_communication", r"nao recebi (?:resposta|retorno)", "I did not receive a response.", "medium"),
    ("packaging", r"mal embalad[oa]", "Poorly packaged.", "medium"),
    ("packaging", r"embalagem (?:original )?(?:toda |muito )?(?:rasgada|danificada|ruim)", "The packaging was torn, damaged or poor.", "medium"),
    ("packaging", r"sem embalagem", "Without packaging.", "medium"),
    ("packaging", r"lacre violado", "The seal was tampered with.", "medium"),
    ("other", r"(?:sem|nao recebi a) nota fiscal", "The invoice was missing/not received.", "medium"),
]
COMPILED = [(category, re.compile(r"\b(?:" + pattern + r")\b"), english, severity)
            for category, pattern, english, severity in RULES]
GENERIC_NEGATIVE = {"ruim": "Bad.", "pessimo": "Terrible.", "pessima": "Terrible.",
    "muito ruim": "Very bad.", "nao gostei": "I did not like it.", "nao recomendo": "I do not recommend it.",
    "horrivel": "Awful.", "insatisfeito": "Dissatisfied.", "insatisfeita": "Dissatisfied."}
POSITIVE = {"bom", "boa", "otimo", "otima", "excelente", "gostei", "entrega no prazo", "uma loja boa"}


def fold_with_offsets(text):
    folded, offsets = [], []
    for index, character in enumerate(text):
        for normalized in unicodedata.normalize("NFD", character.lower()):
            if not unicodedata.combining(normalized):
                folded.append(normalized)
                offsets.append(index)
    return "".join(folded), offsets


def extract_text(text):
    """只对明确文本给出局部事实；没有命中不表示评论没有问题。"""
    if not text.strip():
        return {"issues": [], "sentiment_score": 0.0, "actionable_for_seller": False,
                "confidence": 0.0}, "no_text", False
    folded, offsets = fold_with_offsets(text)
    short = re.sub(r"[^a-z0-9 ]", "", folded).strip()
    short = re.sub(r"\s+", " ", short)
    if short in GENERIC_NEGATIVE:
        return {"issues": [{"category": "other", "severity": "low", "evidence_quote": text.strip(),
                            "evidence_quote_en": GENERIC_NEGATIVE[short]}],
                "sentiment_score": -0.8, "actionable_for_seller": False, "confidence": 0.8}, "generic_sentiment", False
    if short in POSITIVE:
        return {"issues": [], "sentiment_score": 0.6, "actionable_for_seller": False,
                "confidence": 0.6}, "positive_text_low_rating", True
    issues = {}
    for category, pattern, english, severity in COMPILED:
        for match in pattern.finditer(folded):
            prefix = folded[max(0, match.start() - 35):match.start()]
            suffix = folded[match.end():match.end() + 28]
            if re.search(r"(?:sem|nao (?:esta|veio|chegou|tem|apresenta))\s*$", prefix):
                continue
            if category == "missing_item" and re.match(r"\s+(?:(?:a |o |um |uma )?)(?:nota fiscal|resposta|retorno|contato|email|e-mail)", suffix):
                continue
            if category in issues:
                break
            evidence = text[offsets[match.start()]:offsets[match.end() - 1] + 1]
            issues[category] = {"category": category, "severity": severity,
                                "evidence_quote": evidence, "evidence_quote_en": english}
            break
    if not issues:
        return {"issues": [], "sentiment_score": 0.0, "actionable_for_seller": False,
                "confidence": 0.0}, "unresolved", True
    ordered = sorted(issues.values(), key=lambda issue: issue["category"])
    # 这是保守的局部标签，不声称覆盖复杂文本中的全部问题。
    needs_review = len(text) > 120 or "?" in text or len(ordered) > 2
    return {"issues": ordered, "sentiment_score": -0.7,
            "actionable_for_seller": True, "confidence": 0.55 if needs_review else 0.8}, "rule_evidence", needs_review
