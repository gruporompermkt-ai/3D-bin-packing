#!/usr/bin/env bash
# Consulta o Sisplan (SOMENTE LEITURA) usando a conexão do Estoque AR no .95.
#   ./scripts/sisplan.sh extrair > dados/historico/sisplan.json   (histórico completo, inclui "cte")
#   ./scripts/sisplan.sh consulta < consulta.sql                   (uma consulta SELECT)
# As travas de leitura estão em scripts/sisplan.js.
set -euo pipefail
cd "$(dirname "$0")"
HOST="${SISPLAN_HOST:-leonardo@192.168.0.95}"
MODO="${1:-extrair}"
SQL_B64=""
[[ "$MODO" == consulta ]] && SQL_B64=$(base64 -w0)
# o script vai pela entrada padrão do node; a consulta (base64) numa variável de ambiente
ssh "$HOST" "docker exec -i -e CONSULTA_B64=$SQL_B64 -w /app fox-stock-ar-backend node - $MODO" < sisplan.js
