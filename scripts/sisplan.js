// Acesso ao Sisplan para a Cubagem: SOMENTE CONSULTA.
// Roda dentro do container do Estoque AR (que tem o driver pg e a conexão), via scripts/sisplan.sh.
//
// O usuário do banco ("consulta") não tem modo só leitura no próprio papel, e ele não deve ser alterado.
// Então a leitura é forçada aqui, em três camadas:
//   1. a sessão abre com default_transaction_read_only=on (igual ao Estoque AR, backend/src/database/sisplan.ts);
//   2. cada consulta roda dentro de BEGIN READ ONLY ... ROLLBACK;
//   3. só aceita SELECT / WITH, um comando por vez; qualquer outra coisa é recusada antes de ir ao banco.
//
// Uso:  node - extrair           -> JSON com o histórico (fretes, volumes, itens, notas, produtos, cte)
//       node - consulta          -> JSON com as linhas de UMA consulta (SQL em base64 na variável CONSULTA_B64)


const PERIODO = ["2023-01-01", "2026-12-31"];
const PEDIDOS = `(select distinct f.pedido::text from sisplan.frete_cota_001 f
                  where f.data between '${PERIODO[0]}' and '${PERIODO[1]}' and f.valor > 0)`;

const EXTRACAO = {
  fretes: `select f.pedido::text pedido, f.data, f.valor frete, nullif(trim(f.nota_cte),'') nota_cte, f.transp,
             t.nome transportadora, ci.nome cidade, ci.cod_uf uf, coalesce(nullif(e.cep_ent,''), e.cep) cep
           from sisplan.frete_cota_001 f
           left join sisplan.tabtran_001 t on t.codigo = f.transp
           left join sisplan.pedido_001 p on p.numero::text = f.pedido::text
           left join sisplan.entidade_001 e on e.codcli = p.codcli
           left join sisplan.cadcep_001 cep on cep.cep = coalesce(nullif(e.cep_ent,''), e.cep)
           left join sisplan.cidade ci on ci.codigo = cep.codmun
           where f.data between '${PERIODO[0]}' and '${PERIODO[1]}' and f.valor > 0`,
  volumes: `select numero pedido, caixa volume, max(obs) obs, max(peso) peso, max(peso_l) peso_l,
              sum(qtde+coalesce(qtde_f,0)) pecas, max(notafiscal) fatura
            from sisplan.pedido3_001 where numero in ${PEDIDOS} group by 1,2`,
  itens: `select numero pedido, caixa volume, codigo produto, tam, sum(qtde+coalesce(qtde_f,0)) qtde
          from sisplan.pedido3_001 where numero in ${PEDIDOS} group by 1,2,3,4`,
  notas: `select n.fatura, n.dt_emissao, n.val_produtos, n.val_frete, n.pesob, n.pesol, n.volumes, n.cif
          from sisplan.nota_001 n
          where n.fatura in (select notafiscal from sisplan.pedido3_001 where numero in ${PEDIDOS})`,
  produtos: `select codigo, descricao, grupo from sisplan.produto_001
             where codigo in (select codigo from sisplan.pedido3_001 where numero in ${PEDIDOS})`,
  // frete real: CT-e lançado na entrada (tipo 57) ligado à nota de venda, como o relatório R10
  cte: `select distinct ni.pedido::text pedido, nr.nota_ref nota_venda, nr.nota cte, ne.dt_entrada, ne.valor frete_real
        from sisplan.nota_ref_001 nr
        join sisplan.notaiten_001 ni on ni.fatura = nr.nota_ref
        join sisplan.nota_entra_001 ne on ne.notafiscal = nr.nota and ne.tipo = '57'
        where ni.pedido::text in ${PEDIDOS} and ne.valor > 0`,
};

// sem comentários e sem ';' no meio; precisa começar com SELECT ou WITH e não conter comandos de escrita
const PROIBIDO = /\b(insert|update|delete|merge|upsert|create|alter|drop|truncate|grant|revoke|comment|copy|vacuum|analyze|cluster|reindex|refresh|lock|call|do|execute|prepare|set|reset|begin|commit|rollback|savepoint|listen|notify|security|owner)\b/i;

function validar(sql) {
  const limpo = sql.replace(/--[^\n]*/g, ' ').replace(/\/\*[\s\S]*?\*\//g, ' ').trim().replace(/;\s*$/, '');
  if (limpo.includes(';')) throw new Error('recusado: mais de um comando');
  if (!/^(select|with)\b/i.test(limpo)) throw new Error('recusado: só SELECT/WITH');
  // ignora palavras dentro de strings ('...') ao procurar comandos proibidos
  const semTexto = limpo.replace(/'(?:[^']|'')*'/g, "''");
  const achou = semTexto.match(PROIBIDO);
  if (achou) throw new Error(`recusado: contém "${achou[0]}"`);
  return limpo;
}

async function conectar() {
  const { Client } = require('pg');
  const c = new Client({
    connectionString: process.env.SISPLAN_DATABASE_URL,
    options: '-c default_transaction_read_only=on -c statement_timeout=120000 -c search_path=sisplan',
    application_name: 'cubagem-somente-consulta',
  });
  await c.connect();
  const r = await c.query("select current_setting('default_transaction_read_only') ro");
  if (r.rows[0].ro !== 'on') throw new Error('sessão não ficou em somente leitura; abortado');
  return c;
}

async function consultar(c, sql) {
  const ok = validar(sql);
  await c.query('BEGIN READ ONLY');
  try {
    return (await c.query(ok)).rows;
  } finally {
    await c.query('ROLLBACK');
  }
}

async function main() {
  const modo = process.argv[2];
  const c = await conectar();
  try {
    if (modo === 'extrair') {
      const out = {};
      for (const [k, sql] of Object.entries(EXTRACAO)) out[k] = await consultar(c, sql);
      process.stdout.write(JSON.stringify(out));
    } else if (modo === 'consulta') {
      const sql = Buffer.from(process.env.CONSULTA_B64 || '', 'base64').toString('utf8');
      process.stdout.write(JSON.stringify(await consultar(c, sql)));
    } else {
      throw new Error('uso: extrair | consulta');
    }
  } finally {
    await c.end();
  }
}

if (require.main === module || process.argv[1] === '-') {
  main().catch((e) => { process.stderr.write('ERRO ' + e.message + '\n'); process.exit(1); });
}
module.exports = { validar };
