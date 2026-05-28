Comandos para inicializar e parar containers e pods

Pull image do docker hub repository

```bash
sudo crictl pull docker.io/library/redis:alpine
```

Garantir que existam os arquivos de configuração do pod e do container estão na vm

Criar pod conectado ao localhost

```bash
POD_ID=$(sudo crictl runp pod-localhost.json)
echo "Pod ID: $POD_ID"
```

Criar container dentro do pod

```bash
CONTAINER_ID=$(sudo crictl create $POD_ID container-redis.json pod-localhost.json)
echo "Container ID: $CONTAINER_ID"
```

Iniciar o container

```bash
sudo crictl start $CONTAINER_ID
```

Verificar se container está sendo executado

```bash
sudo crictl ps
```

Para visualizar os logs do container

```bash
sudo crictl logs $CONTAINER_ID
```

Rodar checkpoint do container

```bash
sudo crictl checkpoint --export=/tmp/redis-checkpoint.tar $CONTAINER_ID
```

Verificar se o dump foi gerado

```bash
sudo ls -lh /tmp/redis-checkpoint.tar
```

Antes de executar a restauração, precisa limpar os recursos

1. **Parar e remover os containers em execução**

   ```bash
   sudo crictl stop $CONTAINER_ID
   sudo crictl rm $CONTAINER_ID
   ```

2. **Parar e remover o pod sandbox**

   ```bash
   sudo crictl stopp $POD_ID
   sudo crictl rmp $POD_ID
   ```

   _(Cheque o ID do POD usando `sudo crictl pods`)_

## Fase de restaurar

Iniciar um novo Pod Sandbox

```bash
RPOD_ID=$(sudo crictl runp pod-localhost.json)
echo "Pod ID: $POD_ID"
```

Ajustar a image da configuração do container para apontar para o dump

```bash
RCONTAINER_ID=$(sudo crictl create $RPOD_ID container-redis-restore.json pod-localhost.json)
echo "Container ID: $RCONTAINER_ID"
```

Inicia o container

```bash
sudo crictl start $RCONTAINER_ID
```

Verificar a execução do container

```bash
sudo crictl ps
```

Para limpar o pod e container

```bash
sudo crictl stop $CONTAINER_ID
sudo crictl rm $CONTAINER_ID
sudo crictl stopp $POD_ID
sudo crictl rmp $POD_ID
```
