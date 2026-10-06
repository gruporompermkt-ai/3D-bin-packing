-- A Cubagem usa o MESMO usuário de consulta do Estoque AR (estoque_ar_ro), já criado por
-- fox-stock-ar/scripts/criar-usuario-sisplan.sql: só leitura, search_path sisplan.
-- Aqui só se liberam as tabelas extras do histórico. Rodar como administrador do banco no .94.
--
-- Obs.: o papel tem statement_timeout = 5s (bom para o Estoque AR). A extração do histórico faz
-- "SET statement_timeout = '60s'" na própria sessão e roda mês a mês, sem mudar o papel.

GRANT SELECT ON
  sisplan.pedido_001,       -- pedido: cliente, transportadora
  sisplan.caixa_001,        -- tipos de caixa/embalagem (descrição com medidas e peso, tara)
  sisplan.nota_001,         -- nota fiscal: frete (cotação), valor dos produtos, peso, volumes, transportadora, CIF
  sisplan.notaiten_001,     -- itens da nota (liga nota <-> pedido)
  sisplan.tabtran_001,      -- transportadoras
  sisplan.cadcep_001,       -- CEP -> município
  sisplan.cidade            -- município, UF
TO estoque_ar_ro;
-- pedido3_001 e produto_001 o Estoque AR já tem.

-- Cliente: só o necessário para o destino (sem nome, CNPJ, endereço completo)
GRANT SELECT (codcli, cep, cep_ent) ON sisplan.entidade_001 TO estoque_ar_ro;

-- Falta: tabela onde fica o valor do CT-e (custo real do frete). Incluir aqui quando soubermos qual é.
