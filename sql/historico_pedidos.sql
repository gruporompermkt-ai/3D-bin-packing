-- Histórico real para calibrar a cubagem e estimar o frete.
-- Tabelas e colunas tiradas dos logs do Sisplan:
--   LogSelect_LOGISTICA24_FATURAMENTO 0_20261006.log  (Relatório de Expedição de Pedidos, TFMRELEXPPED)
--   LogSelect_MARKETING-2_Marketing_20260903.log      (consulta de faturamento com NOTA.VAL_FRETE)
-- RASCUNHO: ainda não rodado no banco (falta o usuário cubagem_ro). Parâmetros :de e :ate = período.
--
-- Regras vistas no log:
--  * PEDIDO3_001 tem uma linha por item dentro de cada volume; CAIXA = nº do volume (o "CX: 040708"
--    da etiqueta), TCAIXA = tipo da caixa (CAIXA_001.CODIGO), PESO/PESO_L = peso bruto/líquido do
--    VOLUME repetido em cada linha dele (o Sisplan faz DISTINCT CAIXA, PESO).
--  * Pedido de troca vem com 'T' na frente do número em PEDIDO3 (o Sisplan tira o 'T' para achar o pedido).
--  * PEDIDO3.NOTAFISCAL = NOTAITEN.FATURA = NOTA.FATURA.

-- 1) Volumes realmente enviados (um por linha)
SELECT p3.numero                         AS pedido,
       p3.caixa                          AS volume,
       p3.tcaixa                         AS tipo_caixa,
       cx.descricao                      AS desc_caixa,
       cx.peso                           AS tara_caixa,
       MAX(p3.peso)                      AS peso_bruto,
       MAX(p3.peso_l)                    AS peso_liquido,
       SUM(p3.qtde + p3.qtde_f)          AS pecas,
       MAX(p3.notafiscal)                AS fatura
FROM pedido3_001 p3
LEFT JOIN caixa_001 cx ON cx.codigo = p3.tcaixa
WHERE p3.notafiscal IN (SELECT n.fatura FROM nota_001 n WHERE n.dt_emissao BETWEEN :de AND :ate)
GROUP BY p3.numero, p3.caixa, p3.tcaixa, cx.descricao, cx.peso;

-- 2) Itens de cada volume (entrada da cubagem: produto, cor, tamanho, quantidade)
SELECT p3.numero AS pedido, p3.caixa AS volume, p3.codigo AS produto, p3.cor, p3.tam,
       SUM(p3.qtde + p3.qtde_f) AS qtde
FROM pedido3_001 p3
WHERE p3.notafiscal IN (SELECT n.fatura FROM nota_001 n WHERE n.dt_emissao BETWEEN :de AND :ate)
GROUP BY p3.numero, p3.caixa, p3.codigo, p3.cor, p3.tam;

-- 3) Notas: frete, valor, peso, volumes, transportadora e destino (alvo do modelo de frete)
SELECT n.fatura,
       n.dt_emissao,
       n.transport                       AS cod_transportadora,
       t.nome                            AS transportadora,
       n.cif,
       n.redesp                          AS cod_redespacho,
       n.val_frete,
       n.val_produtos,
       n.pesob,
       n.pesol,
       n.volumes,
       ci.nome                           AS cidade,
       ci.cod_uf                         AS uf,
       e.cep,
       (SELECT string_agg(DISTINCT ni.pedido::text, ',') FROM notaiten_001 ni WHERE ni.fatura = n.fatura) AS pedidos
FROM nota_001 n
LEFT JOIN tabtran_001 t ON t.codigo = n.transport
LEFT JOIN LATERAL (SELECT ni.pedido FROM notaiten_001 ni WHERE ni.fatura = n.fatura LIMIT 1) ni1 ON TRUE
LEFT JOIN pedido_001 p ON p.numero = ni1.pedido
LEFT JOIN entidade_001 e ON e.codcli = p.codcli
LEFT JOIN cadcep_001 cep ON cep.cep = COALESCE(NULLIF(e.cep_ent, ''), e.cep)
LEFT JOIN cidade ci ON ci.codigo = cep.codmun
WHERE n.dt_emissao BETWEEN :de AND :ate;
