#!/bin/bash

# filepath: /home/matheus/documents/migration-daemon/load_and_save_dummy_data_chunked.sh

# Variáveis para controlar o tamanho dos dados
NUM_KEYS=50000  # Número de chaves a serem geradas
VALUE_SIZE=10240    # Tamanho de cada valor em bytes
CHUNK_SIZE_MB=50  # Tamanho máximo de cada chunk em MB

# Detalhes de conexão do Redis
REDIS_HOST="172.19.0.4"
REDIS_PORT="6379"

# Arquivo para salvar os comandos Redis
DUMP_FILE="redis_dump_commands.txt"

# Função para gerar uma string aleatória de um tamanho específico
generate_random_string() {
  local size=$1
  tr -dc 'a-zA-Z0-9' </dev/urandom | head -c "$size"
}

# Função para enviar um chunk de dados para o Redis
send_chunk_to_redis() {
  local chunk_file=$1
  echo "Enviando chunk para o Redis..."
  cat "$chunk_file" | redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" --pipe
  echo "Chunk enviado com sucesso."
}

# Gerar comandos Redis e salvar no arquivo
echo "Gerando $NUM_KEYS comandos e salvando em $DUMP_FILE..."
> "$DUMP_FILE" # Limpa o arquivo se já existir
CHUNK_FILE=$(mktemp) # Arquivo temporário para chunks
CHUNK_SIZE_BYTES=$((CHUNK_SIZE_MB * 1024 * 1024)) # Tamanho do chunk em bytes
CURRENT_CHUNK_SIZE=0

value=$(generate_random_string "$VALUE_SIZE")

for ((i = 1; i <= NUM_KEYS; i++)); do
  key="key_$i"
  
  command="SET $key $value"
  
  # Adiciona o comando ao chunk
  echo "$command" >> "$CHUNK_FILE"
  CURRENT_CHUNK_SIZE=$((CURRENT_CHUNK_SIZE + ${#command} + 1)) # Atualiza o tamanho do chunk
  
  # Se o chunk atingir o limite, envia para o Redis
  if ((CURRENT_CHUNK_SIZE >= CHUNK_SIZE_BYTES)); then
    send_chunk_to_redis "$CHUNK_FILE"
    > "$CHUNK_FILE" # Limpa o arquivo temporário
    CURRENT_CHUNK_SIZE=0
  fi
done

# Envia o último chunk, se houver
if ((CURRENT_CHUNK_SIZE > 0)); then
  send_chunk_to_redis "$CHUNK_FILE"
fi

# Salva todos os comandos no arquivo principal
cat "$CHUNK_FILE" >> "$DUMP_FILE"

# Limpa o arquivo temporário
rm -f "$CHUNK_FILE"

echo "Finalizado. Os comandos foram salvos em $DUMP_FILE e enviados para o Redis em chunks de $CHUNK_SIZE_MB MB."