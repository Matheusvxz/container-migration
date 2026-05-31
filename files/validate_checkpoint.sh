#!/bin/bash
set -e

echo "=== 1. Limpando ambiente anterior ==="
sudo crictl ps -q | xargs -r sudo crictl stop || true
sudo crictl ps -a -q | xargs -r sudo crictl rm || true
sudo crictl pods -q | xargs -r sudo crictl stopp || true
sudo crictl pods -q | xargs -r sudo crictl rmp || true
sudo rm -rf /tmp/iter1 /tmp/iter2 /tmp/iter_final /tmp/restore_tar /tmp/redis-checkpoint.tar /tmp/dummy-checkpoint.tar

echo "=== 2. Iniciando contêiner Redis de origem ==="
POD_ID=$(sudo crictl runp /home/matheus/files/pod-localhost.json)
CONTAINER_ID=$(sudo crictl create "$POD_ID" /home/matheus/files/container-redis.json /home/matheus/files/pod-localhost.json)
sudo crictl start "$CONTAINER_ID"

echo "Aguardando o Redis iniciar..."
sleep 3

echo "=== 2.5. Exportando metadados iniciais via crictl checkpoint ==="
# Exportamos os metadados iniciais. O contêiner continua rodando!
sudo crictl checkpoint --export /tmp/dummy-checkpoint.tar "$CONTAINER_ID"

echo "=== 3. Inserindo chave 1 (antes do primeiro pre-dump) ==="
sudo crictl exec "$CONTAINER_ID" redis-cli set key1 "checkpoint_iter_1"
echo "Chave 1 setada. Valor:"
sudo crictl exec "$CONTAINER_ID" redis-cli get key1

echo "=== 4. Executando o primeiro Pre-Dump (iter1) ==="
sudo mkdir -p /tmp/iter1
sudo runc --root /run/runc checkpoint --pre-dump --image-path /tmp/iter1 "$CONTAINER_ID"

echo "=== 5. Inserindo chave 2 (antes do segundo pre-dump) ==="
sudo crictl exec "$CONTAINER_ID" redis-cli set key2 "checkpoint_iter_2"
echo "Chave 2 setada. Valor:"
sudo crictl exec "$CONTAINER_ID" redis-cli get key2

echo "=== 6. Executando o segundo Pre-Dump (iter2) ==="
sudo mkdir -p /tmp/iter2
sudo runc --root /run/runc checkpoint --pre-dump --parent-path ../iter1 --image-path /tmp/iter2 "$CONTAINER_ID"

echo "=== 7. Inserindo chave 3 (antes do checkpoint final) ==="
sudo crictl exec "$CONTAINER_ID" redis-cli set key3 "checkpoint_iter_3"
echo "Chave 3 setada. Valor:"
sudo crictl exec "$CONTAINER_ID" redis-cli get key3

echo "=== 8. Executando o Checkpoint Final (iter_final) ==="
sudo mkdir -p /tmp/iter_final
sudo runc --root /run/runc checkpoint --parent-path ../iter2 --image-path /tmp/iter_final "$CONTAINER_ID"

echo "=== 9. Criando Tarball Auto-Contido ==="
sudo mkdir -p /tmp/restore_tar
sudo tar -C /tmp/restore_tar -xf /tmp/dummy-checkpoint.tar
sudo rm -rf /tmp/restore_tar/checkpoint

sudo cp -a /tmp/iter_final /tmp/restore_tar/checkpoint
sudo cp -a /tmp/iter1 /tmp/restore_tar/iter1
sudo cp -a /tmp/iter2 /tmp/restore_tar/iter2

sudo rm -f /tmp/restore_tar/checkpoint/parent && sudo ln -s ../iter2 /tmp/restore_tar/checkpoint/parent
sudo rm -f /tmp/restore_tar/iter2/parent && sudo ln -s ../iter1 /tmp/restore_tar/iter2/parent

cd /tmp/restore_tar
sudo tar -cf /tmp/redis-checkpoint.tar *
cd -

echo "=== 10. Limpando pod e contêiner antigos ==="
sudo crictl rm "$CONTAINER_ID"
sudo crictl stopp "$POD_ID"
sudo crictl rmp "$POD_ID"

echo "=== 11. Restaurando contêiner de destino ==="
NEW_POD_ID=$(sudo crictl runp /home/matheus/files/pod-localhost.json)
NEW_CONTAINER_ID=$(sudo crictl create "$NEW_POD_ID" /home/matheus/files/container-redis-restore.json /home/matheus/files/pod-localhost.json)
sudo crictl start "$NEW_CONTAINER_ID"

echo "Aguardando o Redis restaurado subir..."
sleep 3

echo "=== 12. Validando a recuperação de todas as chaves ==="
VAL1=$(sudo crictl exec "$NEW_CONTAINER_ID" redis-cli get key1)
VAL2=$(sudo crictl exec "$NEW_CONTAINER_ID" redis-cli get key2)
VAL3=$(sudo crictl exec "$NEW_CONTAINER_ID" redis-cli get key3)

echo "------------------------------------"
echo "Chave 1: $VAL1 (Esperado: checkpoint_iter_1)"
echo "Chave 2: $VAL2 (Esperado: checkpoint_iter_2)"
echo "Chave 3: $VAL3 (Esperado: checkpoint_iter_3)"
echo "------------------------------------"

if [ "$VAL1" == "checkpoint_iter_1" ] && [ "$VAL2" == "checkpoint_iter_2" ] && [ "$VAL3" == "checkpoint_iter_3" ]; then
    echo "SUCESSO: Todas as chaves foram recuperadas com sucesso!"
    exit 0
else
    echo "ERRO: Alguma chave não foi recuperada ou possui valor incorreto!"
    exit 1
fi
