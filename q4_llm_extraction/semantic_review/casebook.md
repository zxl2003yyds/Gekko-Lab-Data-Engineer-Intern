# Q4 复杂语义与完整翻译案例

当前助手逐条分析 60 条既有样本，并翻译完整原文。此处是事后草稿，不是独立人工验收，不改变冻结规则、extracted_issues.json 或原 60 条基准成绩。完整证据和翻译保存在 cases.json。

## 怎样阅读

先看原文与英文，再区分已报告的问题和补救请求；疑点保留在备注中。所有事件均为买家所述，不代表独立确认。没有赋予新的数值置信度。原文中的非标准拼写可在英文中按语境表达，但不得补造日期、型号、责任人或缺失尾句。

## 参考标签的修订

原参考标签也可能有偏差。本轮以下记录按更保守的证据口径修改，保留历史结果，不用新标签重新包装成旧版的测试真值：

- 55444：delivery_late, missing_item → missing_item。暗示可能超期，但没有今天的日期；将 delivery_late 留为歧义候选，不作为确定类别。

- 6341：quality_defect, wrong_product → quality_defect。inferior 更直接是质量比宣传差，没有明确错型号/规格，保守不额外标 wrong_product。

## 原文、翻译和决策

### 源记录 15288

原文（保留原始转义换行）：

```text
Comprei o produto que veio com avarias, estou tentando devolver a mercadoria e a loja esta rejeitando o meu pedido. Estou muito insatisfeito com a loja e com as lannister.
```

完整英文：

I bought the product and it arrived damaged. I am trying to return the goods, but the store is rejecting my request. I am very dissatisfied with the store and with lannister.

问题：quality_defect / medium; other / medium

补救请求：return

情绪：negative；卖家可跟进：True。

损坏和退货申请被拒是两个事实；拒绝申请不等于没有回复。未说明完全无法使用，质量问题按 medium 保守处理。

待澄清：损坏程度及是否影响正常使用未明确

### 源记录 95386

原文（保留原始转义换行）：

```text
O frete é caro e ainda se quiser tem q buscar no correio.Muito ruim.Ainda quer elogios,odiei.
```

完整英文：

Shipping is expensive, and if you still want the item, you have to collect it at the post office. Very bad. They still want compliments; I hated it.

问题：other / medium

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

运费与自取方式投诉归 other；没有明确超时，不标 delivery_late。

### 源记录 80785

原文（保留原始转义换行）：

```text
MUITO BOM PRODUTO EU GOSTEI
```

完整英文：

VERY GOOD PRODUCT. I LIKED IT.

问题：无充分证据支持具体问题

补救请求：未明确提出

情绪：positive；卖家可跟进：False。

正文是正面评价，低分不能反向制造问题。

### 源记录 94005

原文（保留原始转义换行）：

```text
mandaram meu pedido errado ja mandei o email e nao me responderan
```

完整英文：

They sent my order incorrectly. I have already sent an email, and they have not replied.

问题：wrong_product / medium; seller_communication / medium

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

responderan 是拼写错误，语境明确表示未回复；保留过去已发邮件的时间关系。 原文报告已经发送邮件但未获回复，并未明确提出新的联系请求；可跟进不等于已提出请求。

### 源记录 17732

原文（保留原始转义换行）：

```text
Comprei dois e recebi apenas um.
```

完整英文：

I bought two and received only one.

问题：missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

应比较购买量 2 与到货量 1；不能只匹配某个商品名。

### 源记录 71422

原文（保留原始转义换行）：

```text
Produto chego certo, só meu outro produto ainda não chego , 
```

完整英文：

The product arrived correctly; it is just that my other product still has not arrived.

问题：missing_item / high

补救请求：未明确提出

情绪：mixed；卖家可跟进：True。

chego 在此是 chegou 的非规范拼写；一件正常不消除另一件缺失。

### 源记录 11810

原文（保留原始转义换行）：

```text
Comprei duas torres de cerveja, a transportadora só me entregou uma embalagem e que só tinha uma torre dentro, estou muito insatisfeita!
```

完整英文：

I bought two beer towers. The carrier delivered only one package to me, and there was only one tower inside. I am very dissatisfied!

问题：missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

包裹数与商品数分开；缺货结论来自塔数量 2→1，而非仅仅一只包裹。

### 源记录 48681

原文（保留原始转义换行）：

```text
Não é o mesmo produto que fiz o pedido, mas chegou perfeito.
```

完整英文：

It is not the same product that I ordered, but it arrived in perfect condition.

问题：wrong_product / medium

补救请求：未明确提出

情绪：mixed；卖家可跟进：True。

完好描述物理状态，不能否定发错商品。

### 源记录 72677

原文（保留原始转义换行）：

```text
Quero saber se foi cancelada só isso!
```

完整英文：

I want to know whether it was cancelled, that is all!

问题：无充分证据支持具体问题

补救请求：cancellation_status

情绪：unknown；卖家可跟进：True。

这是询问取消状态，没有足够事实判定取消失败或客服失联。

### 源记录 74733

原文（保留原始转义换行）：

```text
Estou avaliando com 2 estrelas pois o produto veio com problema na palmilha.
Estou aguardando contato do fornecedor para efetuar a troca.
```

完整英文：

I am giving it 2 stars because the product arrived with a problem in the insole. I am waiting for the supplier to contact me so that I can exchange it.

问题：quality_defect / medium

补救请求：exchange, contact

情绪：negative；卖家可跟进：True。

鞋垫有问题但未明确完全无法使用，severity 为 medium；等待联系是请求状态，不独立标客服故障。

### 源记录 19847

原文（保留原始转义换行）：

```text
Solicitei Toner CB436A e recebi Toner CB435A, preciso que façam a troca do produto.
```

完整英文：

I requested toner CB436A and received toner CB435A. I need you to exchange the product.

问题：wrong_product / medium

补救请求：exchange

情绪：negative；卖家可跟进：True。

两个型号仅一位不同，必须逐字符保留；不能归因兼容性故障。

### 源记录 50194

原文（保留原始转义换行）：

```text
Estou insatisfeita com a entrega

```

完整英文：

I am dissatisfied with the delivery.

问题：other / low

补救请求：未明确提出

情绪：negative；卖家可跟进：False。

没有给出迟到、丢件或错地址等细节，保留笼统配送不满。

### 源记录 34946

原文（保留原始转义换行）：

```text
O microfone não está funcionando. Tá com um som muito baixo e estranho. O que fazer para utilizar a garantia?

```

完整英文：

The microphone is not working. Its sound is very quiet and strange. What should I do to use the warranty?

问题：quality_defect / high

补救请求：warranty

情绪：negative；卖家可跟进：True。

原文明示不工作，即使另有低音量描述，不能翻译成完全没有声音。

### 源记录 19882

原文（保留原始转义换行）：

```text
O produto não funciona.
```

完整英文：

The product does not work.

问题：quality_defect / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

直接功能故障。

### 源记录 78379

原文（保留原始转义换行）：

```text
O espelho tem uma qualidade péssima. Não é compatível com os espelhos já adquiridos por mim do mesmo modelo (10X).
Solicito a devolução e a restituição do meu pagamento.
```

完整英文：

The mirror is of terrible quality. It is not compatible with the mirrors of the same model (10X) that I have already bought. I request to return it and have my payment refunded.

问题：quality_defect / medium

补救请求：return, refund

情绪：negative；卖家可跟进：True。

不兼容指与此前镜子的比较，未明确实际发错型号；退款是请求，未声明已退款失败。 compatível 保留字面译法，但其比较维度未说明，应由懂葡语的审核者进一步判断。

待澄清：compatível 在此可能指与此前同型号镜子相符或相当，不能确定为物理兼容性问题

### 源记录 89152

原文（保留原始转义换行）：

```text
Meu pedido foi entregue pela metade. As réguas vieram, mas as tesouras não. Aguardo um retorno da loja
```

完整英文：

Only half of my order was delivered. The rulers arrived, but the scissors did not. I am waiting for a response from the store.

问题：missing_item / high

补救请求：contact

情绪：negative；卖家可跟进：True。

缺少的是剪刀；等待回复尚不等于已联系多次无人回应。

### 源记录 88853

原文（保留原始转义换行）：

```text
após saber em cima do prazo que teria de retirar a mercadoria num centro de distribuição do correios que fica há mais de uma hora da minha casa, perdi a mercadoria 
```

完整英文：

After finding out close to the deadline that I would have to collect the goods from a post-office distribution centre more than an hour from my home, I missed out on the goods.

问题：other / medium

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

perdi a mercadoria 可指未能取到/失去这次取货机会，不能擅译为物流公司丢失包裹；具体结果需复核。

待澄清：perdi a mercadoria 的具体丢失/未取到结果

### 源记录 90447

原文（保留原始转义换行）：

```text
Já passou do prazo previsto e nada ainda, o relógio é para presente e a data até passou, se demorarem mais, quero reembolso
```

完整英文：

The expected deadline has already passed, and still nothing has arrived. The watch is a gift, and the date has even passed. If they take any longer, I want a refund.

问题：delivery_late / medium; missing_item / high

补救请求：conditional_refund

情绪：negative；卖家可跟进：True。

退款请求有条件，不能标退款失败；后面的 data 可能指送礼日期或前述期限，不添加具体日期或确定其所指。

待澄清：第二处 data 的具体所指不明确

### 源记录 53792

原文（保留原始转义换行）：

```text
Comprei três produtos e recebi apenas um .
```

完整英文：

I bought three products and received only one.

问题：missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

数量 3→1。

### 源记录 71403

原文（保留原始转义换行）：

```text
O prazo apresentado no momento da compra era um, mas depois que efetuei o pagamento mudou sendo postergado para após o natal. E mesmo assim chegou dois dias depois do informado.
```

完整英文：

One delivery deadline was shown when I made the purchase, but after I paid, it changed and was postponed until after Christmas. Even then, it arrived two days later than stated.

问题：delivery_late / medium

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

已经收到，问题为相对变更后承诺仍迟到；不标当前缺货。

### 源记录 94163

原文（保留原始转义换行）：

```text
Solicitei e JÁ PAGUEI por 02 (DOIS) mochos e recebi apenas 01 (UM)!!!... Aonde eu reclamo???
```

完整英文：

I requested and HAVE ALREADY PAID FOR 02 (TWO) stools (mochos), and I received only 01 (ONE)!!! Where do I complain?

问题：missing_item / high

补救请求：complaint_channel

情绪：negative；卖家可跟进：True。

mocho 的词典义包含无靠背凳；关联商品类别 moveis_escritorio（办公家具）支持在此译为 stools，不能进一步断言是牙科凳等具体款式。数字和强调完整保留。

待澄清：具体凳子款式未在评价中提供

辅助词义证据：关联商品类别为 `moveis_escritorio`（办公家具），词典支持凳子义；此上下文仅用于词义选择。[Priberam 词条](https://dicionario.priberam.org/mocho)。

### 源记录 36992

原文（保留原始转义换行）：

```text
Eu comprei 2 produtos: uma máscara do Hulk e uma mochila do Hulk. Somente a máscara foi entregue. Gostaria de saber como proceder.
```

完整英文：

I bought 2 products: a Hulk mask and a Hulk backpack. Only the mask was delivered. I would like to know what to do.

问题：missing_item / high

补救请求：support

情绪：negative；卖家可跟进：True。

缺少背包，不是数量已经齐全但类别不同。

### 源记录 21415

原文（保留原始转义换行）：

```text
O pedido foi entregue incompleto. Comprei duas capas para o celular moto g5 e duas películas de vidro para o mesmo celular, porém foram entregues somente uma capa e uma película.
```

完整英文：

The order was delivered incomplete. I bought two cases for the moto g5 phone and two glass screen protectors for the same phone, but only one case and one screen protector were delivered.

问题：missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

两个品类各少一件，不能将屏幕保护膜当作手机本身。

### 源记录 19872

原文（保留原始转义换行）：

```text
Fiz um pedido com dois perfumes mas so foi entregue um produto
```

完整英文：

I placed an order for two perfumes, but only one product was delivered.

问题：missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

数量对比可跨从句。

### 源记录 3166

原文（保留原始转义换行）：

```text
loja confiável já havia comprado outra vez
```

完整英文：

A trustworthy store. I had bought from it before.

问题：无充分证据支持具体问题

补救请求：未明确提出

情绪：positive；卖家可跟进：False。

回购与可信评价不应因低分转为投诉。

### 源记录 36313

原文（保留原始转义换行）：

```text
comprei 2 cartuchos ORIGINAIS HP670XL PRETO conforme anunciado no site e entregaram 1 cartucho COMPATÍVEL. Reclamei por site e estou esperando retorno de e-mail. 
```

完整英文：

I bought 2 ORIGINAL BLACK HP670XL cartridges as advertised on the website, and they delivered 1 COMPATIBLE cartridge. I complained through the website and am waiting for an email response.

问题：missing_item / high; wrong_product / medium

补救请求：contact

情绪：negative；卖家可跟进：True。

compatible 在此指兼容替代墨盒，不等同于原装；同时有数量和规格不符。仅等待回复不另认定失联。

### 源记录 31359

原文（保留原始转义换行）：

```text
Eu solicitei uma fôrma de bolo para uma fritadeira elétrica, e na descrição na compra informou o modelo da fritadeira no site, mas me entregaram uma forma minúscula para outro tipo de fritadeira.
```

完整英文：

I requested a cake pan for an electric fryer, and the description on the website stated the fryer model when I bought it, but they delivered a tiny pan for another type of fryer.

问题：wrong_product / medium

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

尺寸小与适配其他机型共同支持规格不符；未声称商品破损。

### 源记录 40022

原文（保留原始转义换行）：

```text
demora na emisão de nota fiscal, e demora na entrega, produto deveria chegar no maximo dia 19/02 , hoje 21/02 produto não chegou a unidade de Recife PE, imagina quando vai chegar em minha casa?

```

完整英文：

There is a delay in issuing the invoice and a delay in delivery. The product should have arrived by 19/02 at the latest. Today is 21/02, and the product has not reached the Recife, PE facility. Imagine when it will reach my home?

问题：other / medium; delivery_late / medium; missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

明确同时给出承诺日与当前日，足以判超期；不添加原文没有的年份。开票慢是独立问题。

### 源记录 5765

原文（保留原始转义换行）：

```text
Preço atraente, mas demora demais a entrega e não tem acompanhamento via e-mail de por onde o produto anda
```

完整英文：

An attractive price, but delivery takes far too long, and there are no email updates about where the product is.

问题：delivery_late / medium; seller_communication / medium

补救请求：未明确提出

情绪：mixed；卖家可跟进：True。

没有物流邮件更新是明确的信息缺失；不同于仅表示正在等回复。

### 源记录 57364

原文（保留原始转义换行）：

```text
mercadoria se encontrava aqui para a entrega e foi marar no MATO GROSSO e até hj 23/12/2017 não chegou em minha residência.
```

完整英文：

The goods were here for delivery, but then ended up in MATO GROSSO, and as of today, 23/12/2017, they still have not arrived at my home.

问题：missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

marar 按上下文为非规范表达，意为去了别处；未提供承诺日期，不能单凭当前日判超期。

### 源记录 98086

原文（保留原始转义换行）：

```text
O produto não atendeu minhas respectivas, mais o prazo ocorreu antes da data prevista.
```

完整英文：

The product did not meet my expectations, but it arrived before the expected date.

问题：other / low

补救请求：未明确提出

情绪：mixed；卖家可跟进：False。

respectivas 按语境理解为 expectativas，标记原文错词；未说明具体质量问题。

待澄清：respectivas 原文疑似误词

### 源记录 7918

原文（保留原始转义换行）：

```text
Não me enviaram a cor na qual tinha solicitado.
```

完整英文：

They did not send me the colour that I had requested.

问题：wrong_product / medium

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

不是未收到任何商品，而是收到的颜色不符。

### 源记录 56551

原文（保留原始转义换行）：

```text
Comprei 2 chaleiras com infusor mas a empresa só Entregou uma. ainda estou com a caixa pequena para provar que só recebi um dos produtos. Quero reembolso ou entrega urgente da outra chaleira
```

完整英文：

I bought 2 teapots with infusers, but the company delivered only one. I still have the small box to prove that I received only one of the products. I want a refund or urgent delivery of the other teapot.

问题：missing_item / high

补救请求：refund_or_delivery_of_remaining_item

情绪：negative；卖家可跟进：True。

退款与补发是二选一的补救请求，不额外断言退款失败。 明确请求退款或紧急交付另一件；不额外断定必须重新寄出替代品。

### 源记录 66558

原文（保留原始转义换行）：

```text
nao compro mais neste site
```

完整英文：

I will not buy from this website again.

问题：other / low

补救请求：未明确提出

情绪：negative；卖家可跟进：False。

明确负面意向但没有具体故障。

### 源记录 21612

原文（保留原始转义换行）：

```text
Estou no aguardo da entrega da mercadoria que ainda não recebi.
```

完整英文：

I am waiting for delivery of the goods, which I still have not received.

问题：missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

明确未收到，而非仅询问预计时效。

### 源记录 56797

原文（保留原始转义换行）：

```text
Obrigado 
```

完整英文：

Thank you.

问题：无充分证据支持具体问题

补救请求：未明确提出

情绪：positive；卖家可跟进：False。

感谢文本，不提取问题。

### 源记录 19155

原文（保留原始转义换行）：

```text
Não recebi o produto e nem reembolso
```

完整英文：

I have received neither the product nor a refund.

问题：missing_item / high; other / medium

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

商品和退款均未收到是明确事实；区别于“如果不到就退款”。 商品与退款均未收到是并列事实，不改写成买家提出退款或发货二选一的请求。

### 源记录 66078

原文（保留原始转义换行）：

```text
O prazo de entraga poderia ser menor.
O prazo foi cumprido.
O produto veio corretamente .
```

完整英文：

The delivery lead time could be shorter. The deadline was met. The product arrived correctly.

问题：无充分证据支持具体问题

补救请求：未明确提出

情绪：mixed；卖家可跟进：False。

改进愿望不等于实际迟到；整体混合但无明确故障。

### 源记录 44885

原文（保留原始转义换行）：

```text
O material não é muito bom.
```

完整英文：

The material is not very good.

问题：quality_defect / medium

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

not very good 不应译成非常差；质量评价强度保留。

### 源记录 13161

原文（保留原始转义换行）：

```text
Meu produto veio errado outro modelo fui trocar não tem mais
```

完整英文：

My product arrived incorrectly; it was another model. I went to exchange it, but it is no longer available.

问题：wrong_product / medium; other / medium

补救请求：exchange

情绪：negative；卖家可跟进：True。

后句省略主语，解释为所需替换品没有了；缺货范围需人工确认。

待澄清：não tem mais 省略了缺货对象

### 源记录 58721

原文（保留原始转义换行）：

```text
A embalagem parece original, mas logo após a instalação a própria impressora informa que o suprimento NÃO É HP. No cartucho falta indicação da cor e o nome HP vem numa etiqueta de papel e não pintada.
```

完整英文：

The packaging appears to be original, but immediately after installation, the printer itself says that the supply is NOT HP. The cartridge has no colour indication, and the HP name appears on a paper label rather than being painted on the cartridge.

问题：other / medium

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

这是买家怀疑原装身份的证据，不能译成已由平台鉴定为假货；HP 否定归属为打印机提示。

### 源记录 31377

原文（保留原始转义换行）：

```text
O material é excelente,simples,acabamento razoável,flexivel, entregue no último dia do prazo válido por 3 semanas. No entanto quero devolver o produto por não responder com a expectativa

```

完整英文：

The material is excellent, simple, with a reasonable finish and flexible. It was delivered on the last day of the three-week delivery window. However, I want to return the product because it does not meet my expectations.

问题：other / low

补救请求：return

情绪：mixed；卖家可跟进：True。

最后一天仍属按时，reasonable finish 不译为缺陷；不合个人预期归 other。

### 源记录 64521

原文（保留原始转义换行）：

```text
Não chegou tudo o que eu pedi e consta como se estivesse entregue 
```

完整英文：

Not everything I ordered arrived, but it is shown as if it had been delivered.

问题：missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

状态与实际收货不一致；不推断责任方或故意造假。

### 源记录 50977

原文（保留原始转义换行）：

```text
nao recebi meu produto
```

完整英文：

I have not received my product.

问题：missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

缺货，没有承诺时间信息。

### 源记录 5592

原文（保留原始转义换行）：

```text
O produto não foi entregue!
```

完整英文：

The product was not delivered!

问题：missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

未交付。

### 源记录 93983

原文（保留原始转义换行）：

```text
só achei que era de borracha e não de plástico
```

完整英文：

I just thought it was made of rubber, not plastic.

问题：other / low

补救请求：未明确提出

情绪：negative；卖家可跟进：False。

个人以为的材质不等于广告明确承诺，不标规格欺诈或发错货。

### 源记录 83559

原文（保留原始转义换行）：

```text
O controle veio errado eu pedi controle de home theater da Philco 660n e veio LE- 798.
Como faço para trocar?
```

完整英文：

The remote control that arrived was wrong. I ordered a remote for a Philco 660n home theatre system, and an LE- 798 arrived. How do I exchange it?

问题：wrong_product / medium

补救请求：exchange

情绪：negative；卖家可跟进：True。

型号与大小写按原文保留；不能把 home theater 翻译成电影院。

### 源记录 61066

原文（保留原始转义换行）：

```text
Só posso avaliar a loja depois da conclusão do meu pedido .eu já estava sonhando com minha pia .Não sei se a culpa e da loja ou dos correios .mais não recebi meu produto
```

完整英文：

I can only assess the store after my order is completed. I was already dreaming about my sink. I do not know whether the store or the post office is at fault, but I have not received my product.

问题：missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

明确不知道责任方；不得自动归责卖家或物流。

### 源记录 87295

原文（保留原始转义换行）：

```text
estou bem chateada
```

完整英文：

I am very upset.

问题：other / low

补救请求：未明确提出

情绪：negative；卖家可跟进：False。

泛泛情绪，不能编造原因。

### 源记录 88408

原文（保留原始转义换行）：

```text
Sinceramente eu não recomendaria porque meu produto chegou só a metade cadê a empresária nada sexy da autora Deby Incour? Só mudarei minha opinião quando estiver com esse livro
```

完整英文：

Honestly, I would not recommend it because only half of what I ordered arrived. Where is 'a empresária nada sexy' by author Deby Incour? I will only change my opinion once I have this book.

问题：missing_item / high

补救请求：missing_book_status

情绪：negative；卖家可跟进：True。

书名与作者原样保留；“一半”按下文缺一本书理解，不译成一本书被切成半本。 cadê 是询问缺少的书在哪里；后句表达收到书才改评价，不直接等同于要求重新寄出。

### 源记录 90314

原文（保留原始转义换行）：

```text
Acho que está demorando muito
```

完整英文：

I think it is taking a very long time.

问题：other / low

补救请求：未明确提出

情绪：negative；卖家可跟进：False。

未说明是配送、审批或其他环节，保留歧义而不强制标配送迟到。

### 源记录 67174

原文（保留原始转义换行）：

```text
faltou cupom fiscal
```

完整英文：

The sales receipt was missing.

问题：other / medium

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

cupom fiscal 是购物税务小票，不是折扣券；票据缺失不属于商品缺件。 缺少票据是事实；补开票据可作为后续处理，但原文未明确提出该动作。

### 源记录 55444

原文（保留原始转义换行）：

```text
Até hoje nada. Prazo era até dia 26
```

完整英文：

Still nothing as of today. The deadline was the 26th.

问题：missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

暗示可能超期，但没有今天的日期；将 delivery_late 留为歧义候选，不作为确定类别。

待澄清：delivery_late：今天的日期未提供

### 源记录 77864

原文（保留原始转义换行）：

```text
Produto não respondeu às minhas expectativas ,Bem diferente do site
```

完整英文：

The product did not meet my expectations. It is very different from what was shown on the website.

问题：wrong_product / medium

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

与网站展示有明显差异，超过单纯个人期望；差异的具体维度未说明。

### 源记录 6341

原文（保留原始转义换行）：

```text
O produto é inferior ao anunciado,baixa qualidade 
```

完整英文：

The product is inferior to what was advertised and is of low quality.

问题：quality_defect / medium

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

inferior 更直接是质量比宣传差，没有明确错型号/规格，保守不额外标 wrong_product。

待澄清：wrong_product：质量不及广告不必然是错货

### 源记录 55871

原文（保留原始转义换行）：

```text
Não foi entregue o produto. Estava previsto para 27/08 
```

完整英文：

The product was not delivered. It was expected on 27/08.

问题：missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

无评价当天时间，不能为日期补年份或确定已超期。

待澄清：delivery_late：缺当前日期及年份

### 源记录 52770

原文（保留原始转义换行）：

```text
comprei o produto e até agora nada, dizem q está nos correios, se fosse pra eu buscar em algum lugar, teria comprado em loja física
```

完整英文：

I bought the product, and so far nothing has arrived. They say it is at the post office. If I were going to collect it somewhere, I would have bought it from a physical store.

问题：missing_item / high; other / medium

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

条件句表达对自取安排的不满，不是新下单计划。

### 源记录 51500

原文（保留原始转义换行）：

```text
Não recebi meu produto
```

完整英文：

I have not received my product.

问题：missing_item / high

补救请求：未明确提出

情绪：negative；卖家可跟进：True。

缺货。

### 源记录 73576

原文（保留原始转义换行）：

```text
Ótimo prazo de entrega, até porque foi antecipado. Porém, como escolhi outros produtos além dos dois que chegaram - não posso que como cliente fiquei satisfeita.
```

完整英文：

The delivery time was excellent; it was even early. However, I selected other products besides the two that arrived, so I cannot say that I am satisfied as a customer.

问题：missing_item / high

补救请求：未明确提出

情绪：mixed；卖家可跟进：True。

原文缺词，按上下文补足 cannot say that；早到仅适用于已到两件，不代表全部履约。

待澄清：原文 não posso que 有省略/错写

### 源记录 41239

原文（保留原始转义换行）：

```text
A loja está sendo bem correta comigo. Vou devolver o produto. O anúncio dava a entender que era o relógio. Mostravá fotos do relógio, descrição das funções e a redução de preço de 899 por 250
```

完整英文：

The store has been treating me quite fairly. I am going to return the product. The advertisement gave the impression that it was the watch: it showed pictures of the watch, a description of its functions, and a price reduction from 899 to 250.

问题：other / medium

补救请求：return

情绪：mixed；卖家可跟进：True。

投诉对象是广告给人的印象；原文没有交代实际收到的物品，不虚构手机、手表配件等。

## 后续验收

独立审核者应先在盲审包中按原文标注，再看完整译文检查否定、数量、型号、时间、请求与事实是否保留。review_campaign.py 生成两个独立填写包并检查完成度、分歧和翻译问题；没有真人提交时状态保持 pending，准确率为空。
