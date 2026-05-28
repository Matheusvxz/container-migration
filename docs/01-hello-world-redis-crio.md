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

Para limpar o pod e container

```bash
sudo crictl stop $CONTAINER_ID
sudo crictl rm $CONTAINER_ID
sudo crictl stopp $POD_ID
sudo crictl rmp $POD_ID
```
