# Pendências — Cubagem (3D-bin-packing, branch cubagem-vestuario)

**PROJETO DESCONTINUADO em 13/10/2026** (decisão do Jonatas). A rotina diária não acompanha mais este projeto.

Atualizado em 13/10/2026 pela rotina diária (briefing da manhã). Pode editar à vontade: a rotina só reorganiza e acrescenta.

## Falta fazer
- Nada. O que continuava aberto foi para o Fretes (`fox-fretes/PENDENCIAS.md`):
  - Cadastrar as medidas dos produtos na planilha `dados/Cubagem - medidas dos produtos.xlsx` (só 2 referências cadastradas). Sem isso, pedido só lançado não calcula frete sozinho no Fretes. → transferido para o Fretes em 13/10.
  - Decidir se a planilha `dados/Cubagem - medidas dos produtos.xlsx` entra no repositório: ela está fora do git (não versionada). → vai junto com o item acima (decidir onde a planilha passa a ficar).

## Feito
- 07/10/2026 — Estimativa de frete na tela de Cubagem.
- 07/10/2026 — Acesso ao Sisplan só por `scripts/sisplan.sh`, forçando somente consulta.
- 07/10/2026 — Etapa 0 da inteligência de fretes: mapeamento dos dados no Sisplan (versão mantida no fox-fretes).
- 07/10/2026 — Calibração da F2505 documentada (compressão 0,7, lateral 0,92) e modelo de frete.
- 06/10/2026 — Fardos: modos em grade de células, fardo de manga, escolha de caixa ou fardo, peças deitadas e compressão lateral; modelo de frete treinado no histórico real.
