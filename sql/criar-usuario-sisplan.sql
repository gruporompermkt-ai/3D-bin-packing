-- Usuário próprio da Cubagem no Postgres do Sisplan (192.168.0.94, banco 15037P), só leitura.
-- Rodar como administrador do banco. Troque SENHA_FORTE_AQUI antes de rodar; a senha vai só no
-- .env do servidor .95 (/opt/cubagem/.env), nunca no repositório.
-- Mesmo padrão do Estoque AR (fox-stock-ar/scripts/criar-usuario-sisplan.sql).

CREATE ROLE cubagem_ro LOGIN PASSWORD 'SENHA_FORTE_AQUI'
  CONNECTION LIMIT 5;

ALTER ROLE cubagem_ro SET default_transaction_read_only = on;
ALTER ROLE cubagem_ro SET statement_timeout = '60s';       -- extração do histórico (lotes por mês)
ALTER ROLE cubagem_ro SET search_path = sisplan;

GRANT CONNECT ON DATABASE "15037P" TO cubagem_ro;
GRANT USAGE ON SCHEMA sisplan TO cubagem_ro;

GRANT SELECT ON
  sisplan.pedido3_001,      -- expedição: itens em cada volume (CAIXA), peso bruto/líquido do volume
  sisplan.pedido_001,       -- pedido: cliente, transportadora, emissão
  sisplan.caixa_001,        -- tipos de caixa/embalagem (descrição, tara)
  sisplan.nota_001,         -- nota fiscal: valor do frete, valor dos produtos, peso, volumes, transportadora, CIF
  sisplan.notaiten_001,     -- itens da nota (liga nota <-> pedido)
  sisplan.tabtran_001,      -- transportadoras
  sisplan.produto_001,      -- peso do produto
  sisplan.cadcep_001,       -- CEP -> município
  sisplan.cidade            -- município, UF
TO cubagem_ro;

-- Cliente: só o necessário para o destino (sem nome, CNPJ, endereço completo)
GRANT SELECT (codcli, cep, cep_ent) ON sisplan.entidade_001 TO cubagem_ro;

-- Se o pg_hba.conf do .94 restringir por usuário/IP, liberar:
--   host  15037P  cubagem_ro  192.168.0.95/32  scram-sha-256
