#!/bin/bash
# Faz upload do banco local para o volume Fly.io
# Uso: bash scripts/upload_db.sh

echo "Fazendo upload do banco para Fly.io..."
fly ssh sftp shell
# Dentro do shell: put data/sentinela_rj.db /data/sentinela_rj.db
echo "Concluído. Verifique com: fly ssh console -C 'ls -la /data/'"
