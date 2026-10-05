#!/usr/bin/env bash
# Atualiza e sobe a Cubagem no .95:  ./scripts/deploy.sh
# Usa "docker build" direto porque o "docker compose build" do .95 exige um
# buildx mais novo que o do Debian (0.13). Os testes rodam dentro do build.
set -euo pipefail
cd "$(dirname "$0")/.."

git pull -q --ff-only
echo ">> $(git log --oneline -1)"
mkdir -p data && chmod 777 data   # o container roda como usuário sem privilégio (uid 10001)
docker build -q -t cubagem:local . >/dev/null && echo ">> imagem ok (testes passaram)"
docker compose up -d --no-build --force-recreate

for _ in $(seq 1 20); do
  [[ "$(docker inspect -f '{{.State.Health.Status}}' cubagem 2>/dev/null)" == healthy ]] && break
  sleep 2
done
docker compose ps --format '{{.Name}}  {{.Status}}'
docker image prune -f >/dev/null 2>&1 || true
