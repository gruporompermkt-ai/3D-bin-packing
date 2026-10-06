-- Histórico real para calibrar a cubagem e estimar o frete.
-- Conexão: a mesma do Estoque AR (/opt/fox-stock-ar/.env no .95). Abrir a sessão com
--   SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY; SET statement_timeout = '60s';
-- Parâmetros :de e :ate = período (rodar mês a mês).
--
-- O que foi verificado no banco (06/10/2026):
--  * Um pedido pode ter vários volumes. PEDIDO3_001 tem uma linha por item dentro de cada volume;
--    CAIXA = nº do volume (o "CX: 040708" da etiqueta); PESO/PESO_L = peso do VOLUME, repetido nas linhas.
--  * Medidas do volume: só no PEDIDO3.OBS, digitadas ("FD: 52X42X93 CM", "CX: 08X20X28 CM"), lidas por
--    app/historico.py. CAIXA_001 está vazia, TCAIXA em branco e PEDIDO3.ALTURA/LARGURA/COMPRIMENTO zerados.
--    "DENTRO DO OUTRO PEDIDO"/"JUNTO COM O OUTRO PEDIDO" = foi dentro de outro volume.
--  * Frete por pedido: FRETE_COTA_001 (tela de frete): PEDIDO, TRANSP, VALOR, NOTA_CTE (preenchido desde
--    01/2026). ~3.200 pedidos de 2023 a 2026 com frete + medidas + peso de todos os volumes
--    (2023: 2.046; 2024: 33; 2025: 493; 2026: 604). Quase nada entre 07/2024 e 08/2025.
--  * NOTA.VAL_FRETE é a cotação destacada na nota e vem 0 na maioria das notas.
--  * Pedido de troca vem com 'T' na frente do número em PEDIDO3.
--  * PEDIDO3.NOTAFISCAL = NOTAITEN.FATURA = NOTA.FATURA.

-- 1) Volumes realmente enviados (um por linha); medidas saem do obs
SELECT p3.numero                         AS pedido,
       p3.caixa                          AS volume,
       MAX(p3.obs)                       AS obs,
       MAX(p3.peso)                      AS peso_bruto,
       MAX(p3.peso_l)                    AS peso_liquido,
       SUM(p3.qtde + COALESCE(p3.qtde_f, 0)) AS pecas,
       MAX(p3.notafiscal)                AS fatura
FROM pedido3_001 p3
WHERE p3.numero IN (SELECT f.pedido::text FROM frete_cota_001 f WHERE f.data BETWEEN :de AND :ate)
GROUP BY p3.numero, p3.caixa;

-- 2) Itens de cada volume (entrada da cubagem: produto, cor, tamanho, quantidade)
SELECT p3.numero AS pedido, p3.caixa AS volume, p3.codigo AS produto, p3.cor, p3.tam,
       SUM(p3.qtde + COALESCE(p3.qtde_f, 0)) AS qtde
FROM pedido3_001 p3
WHERE p3.numero IN (SELECT f.pedido::text FROM frete_cota_001 f WHERE f.data BETWEEN :de AND :ate)
GROUP BY p3.numero, p3.caixa, p3.codigo, p3.cor, p3.tam;

-- 3) Frete de cada pedido (alvo do modelo) com transportadora e destino
SELECT f.pedido,
       f.data,
       f.valor                           AS frete,
       NULLIF(TRIM(f.nota_cte), '')      AS nota_cte,
       f.transp                          AS cod_transportadora,
       t.nome                            AS transportadora,
       ci.nome                           AS cidade,
       ci.cod_uf                         AS uf,
       COALESCE(NULLIF(e.cep_ent, ''), e.cep) AS cep
FROM frete_cota_001 f
LEFT JOIN tabtran_001 t   ON t.codigo = f.transp
LEFT JOIN pedido_001 p    ON p.numero = f.pedido::text
LEFT JOIN entidade_001 e  ON e.codcli = p.codcli
LEFT JOIN cadcep_001 cep  ON cep.cep = COALESCE(NULLIF(e.cep_ent, ''), e.cep)
LEFT JOIN cidade ci       ON ci.codigo = cep.codmun
WHERE f.data BETWEEN :de AND :ate AND f.valor > 0;

-- 4) Nota do pedido: valor da mercadoria, cotação, peso e volumes declarados
SELECT n.fatura, n.dt_emissao, n.val_produtos, n.val_frete AS frete_cotacao, n.pesob, n.pesol, n.volumes,
       n.cif, n.redesp AS cod_redespacho
FROM nota_001 n
WHERE n.fatura IN (SELECT p3.notafiscal FROM pedido3_001 p3
                   WHERE p3.numero IN (SELECT f.pedido::text FROM frete_cota_001 f WHERE f.data BETWEEN :de AND :ate));
