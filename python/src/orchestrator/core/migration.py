import asyncio
import os
import logging
import uuid
import time
from typing import Dict, List, Optional
import asyncssh

from orchestrator.models import Node, Container, ContainerState, NodeStatus, MigrationJob
from orchestrator.drivers.cri import CRICliClient
from orchestrator.drivers.runc import RuncClient
from orchestrator.core.storage import StorageManager

logger = logging.getLogger(__name__)

class MigrationManager:
    """
    O Orquestrador Central de Migrações.
    Mantém o estado em memória dos nós, contêineres e jobs ativos.
    Fornece APIs não-bloqueantes assíncronas para orquestrar as migrações.
    """
    def __init__(self, key_path: str, username: str = "dev", hosts_file: Optional[str] = None):
        self.key_path = key_path
        self.username = username
        self.hosts_file = hosts_file
        self.nodes: Dict[str, Node] = {}
        self.connections: Dict[str, asyncssh.SSHClientConnection] = {}
        self.jobs: Dict[str, MigrationJob] = {}
        
        # Inicializa os sub-clientes
        self.cri_client = CRICliClient()
        self.runc_client = RuncClient()
        self.storage_manager = StorageManager()

        # Lê o conteúdo da chave privada para passar ao storage manager
        with open(key_path, "r") as f:
            self.private_key_content = f.read()

    async def add_node(self, ip: str) -> None:
        """Adiciona um nó ao monitoramento sem bloquear."""
        if ip not in self.nodes:
            self.nodes[ip] = Node(ip=ip, status=NodeStatus.UNKNOWN)

    async def remove_node(self, ip: str) -> None:
        """Remove um nó do monitoramento e fecha a conexão SSH correspondente."""
        if ip in self.connections:
            conn = self.connections.pop(ip)
            logger.info(f"Fechando conexão SSH com o nó removido {ip}")
            conn.close()
            await conn.wait_closed()
        if ip in self.nodes:
            self.nodes.pop(ip)

    async def set_nodes(self, ips: List[str]) -> None:
        """Define a lista de nós monitorados, conectando aos novos e removendo os ausentes."""
        current_ips = list(self.nodes.keys())
        
        ips_set = set(ips)
        current_set = set(current_ips)
        
        to_remove = current_set - ips_set
        to_add = ips_set - current_set
        to_keep = current_set & ips_set
        
        for ip in to_remove:
            await self.remove_node(ip)
            
        tasks = []
        for ip in to_add:
            await self.add_node(ip)
            tasks.append(self._connect_and_scan_node(ip))
            
        for ip in to_keep:
            tasks.append(self.scan_node_containers(ip))
            
        if tasks:
            await asyncio.gather(*tasks)

    async def add_dynamic_node(self, ip: str) -> None:
        """Adiciona um nó dinamicamente, estabelece conexão SSH, varre os contêineres e persiste a lista."""
        if ip in self.nodes:
            # Se já existir e estiver ONLINE, apenas fazemos re-scan de contêineres
            if self.nodes[ip].status == NodeStatus.ONLINE:
                await self.scan_node_containers(ip)
                self.persist_hosts()
                return
        
        await self.add_node(ip)
        await self._connect_and_scan_node(ip)
        self.persist_hosts()

    async def remove_dynamic_node(self, ip: str) -> None:
        """Remove um nó dinamicamente, fecha a conexão e persiste a lista."""
        await self.remove_node(ip)
        self.persist_hosts()

    async def set_dynamic_nodes(self, ips: List[str]) -> None:
        """Define a lista de nós, reconecta/varre os necessários, remove os ausentes e persiste a lista."""
        await self.set_nodes(ips)
        self.persist_hosts()

    def persist_hosts(self) -> None:
        """Salva a lista atual de IPs de nós de volta no arquivo de hosts."""
        if not self.hosts_file:
            return
        try:
            logger.info(f"Persistindo a nova lista de hosts em {self.hosts_file}...")
            with open(self.hosts_file, "w") as f:
                f.write("# Lista de hosts atualizada dinamicamente pelo orquestrador\n")
                for ip in self.nodes.keys():
                    f.write(f"{ip}\n")
        except Exception as e:
            logger.error(f"Erro ao persistir arquivo de hosts {self.hosts_file}: {e}")

    async def initialize_connections(self, ips: List[str]) -> None:
        """
        Percorre cada nó de forma paralela no startup,
        inicializa as variáveis e verifica contêineres em execução.
        """
        logger.info(f"Inicializando conexões para os nós: {ips}")
        tasks = []
        for ip in ips:
            await self.add_node(ip)
            tasks.append(self._connect_and_scan_node(ip))
        
        # Executa em paralelo de forma não-bloqueante
        await asyncio.gather(*tasks)

    async def _connect_and_scan_node(self, ip: str) -> None:
        """Conecta a um nó individual, descobre contêineres e atualiza seu estado."""
        node = self.nodes[ip]
        try:
            logger.info(f"Estabelecendo conexão SSH com o nó {ip}...")
            # Estabelece conexão sem verificação de known_hosts para automação simples em lab
            conn = await asyncssh.connect(
                ip,
                username=self.username,
                client_keys=[self.key_path],
                known_hosts=None,
                connect_timeout=10
            )
            self.connections[ip] = conn
            node.status = NodeStatus.ONLINE
            logger.info(f"Nó {ip} está ONLINE. Iniciando varredura de contêineres...")

            # Descobre contêineres e pods ativos via CRI
            await self.scan_node_containers(ip)
            
        except Exception as e:
            node.status = NodeStatus.OFFLINE
            node.error_msg = str(e)
            logger.error(f"Falha ao conectar no nó {ip}: {e}")

    async def scan_node_containers(self, ip: str) -> None:
        """Varre o nó buscando pods e contêineres ativos."""
        node = self.nodes[ip]
        conn = self.connections.get(ip)
        if not conn or node.status != NodeStatus.ONLINE:
            return

        try:
            containers_raw = await self.cri_client.list_containers(conn)
            # Limpa contêineres antigos em memória
            node.containers.clear()

            for c_raw in containers_raw:
                c_id = c_raw.get("id")
                c_name = c_raw.get("metadata", {}).get("name", "unknown")
                pod_id = c_raw.get("podSandboxId", "")
                
                # Mapeamento do status
                state_str = c_raw.get("state")
                state = ContainerState.UNKNOWN
                if state_str == "CONTAINER_RUNNING":
                    state = ContainerState.RUNNING
                elif state_str == "CONTAINER_EXITED":
                    state = ContainerState.STOPPED

                image = c_raw.get("image", {}).get("image", "")
                labels = c_raw.get("labels", {})
                annotations = c_raw.get("annotations", {})

                container = Container(
                    id=c_id,
                    name=c_name,
                    pod_id=pod_id,
                    state=state,
                    image=image,
                    node_ip=ip,
                    labels=labels,
                    annotations=annotations
                )
                node.containers[c_id] = container
                logger.info(f"Contêiner detectado no nó {ip}: {c_name} (ID: {c_id[:12]}) - Status: {state.value}")

        except Exception as e:
            logger.error(f"Erro ao varrer contêineres no nó {ip}: {e}")
            raise

    async def close_connections(self) -> None:
        """Fecha todas as conexões SSH de forma limpa."""
        for ip, conn in self.connections.items():
            logger.info(f"Fechando conexão SSH com o nó {ip}")
            conn.close()
            await conn.wait_closed()
        self.connections.clear()

    async def migrate_container(
        self,
        container_id: str,
        source_ip: str,
        target_ip: str,
        pre_dumps_count: int = 2,
        pod_config_local_path: str = "/home/dev/files/pod-localhost.json",
        container_restore_local_path: str = "/home/dev/files/container-redis-restore.json"
    ) -> str:
        """
        Orquestra a migração assíncrona de um contêiner de forma totalmente não-bloqueante.
        Retorna o job_id do processo de migração para acompanhamento do progresso.
        """
        job_id = str(uuid.uuid4())
        job = MigrationJob(
            job_id=job_id,
            container_id=container_id,
            source_ip=source_ip,
            target_ip=target_ip,
            status="PENDING",
            step="INITIALIZING",
            start_time=time.time()
        )
        self.jobs[job_id] = job

        # Cria uma tarefa em background para executar a migração assincronamente
        # Isso garante que a chamada retorne imediatamente e permita migrações simultâneas!
        asyncio.create_task(
            self._execute_migration_workflow(
                job_id,
                container_id,
                source_ip,
                target_ip,
                pre_dumps_count,
                pod_config_local_path,
                container_restore_local_path
            )
        )
        return job_id

    async def _execute_migration_workflow(
        self,
        job_id: str,
        container_id: str,
        source_ip: str,
        target_ip: str,
        pre_dumps_count: int,
        pod_config_local_path: str,
        container_restore_local_path: str
    ) -> None:
        """Implementação interna do fluxo assíncrono passo-a-passo da migração."""
        job = self.jobs[job_id]
        job.status = "IN_PROGRESS"
        
        source_conn = self.connections.get(source_ip)
        target_conn = self.connections.get(target_ip)

        if not source_conn or not target_conn:
            job.status = "FAILED"
            job.error_msg = f"Conexões de origem ({source_ip}) ou destino ({target_ip}) não disponíveis."
            logger.error(job.error_msg)
            return

        # Verifica se o container existe na origem (suportando IDs curtos/prefixos)
        source_node = self.nodes.get(source_ip)
        found_id = None
        if source_node:
            for c_id in source_node.containers:
                if c_id.startswith(container_id):
                    found_id = c_id
                    break

        if not source_node or not found_id:
            job.status = "FAILED"
            job.error_msg = f"Contêiner {container_id[:12]} não encontrado no nó de origem {source_ip}."
            logger.error(job.error_msg)
            return

        container = source_node.containers[found_id]
        container_id = found_id
        job.container_id = found_id
        old_pod_id = container.pod_id

        # Caminhos temporários usados no processo
        temp_dir = "/tmp"
        dummy_checkpoint_tar = f"{temp_dir}/dummy-checkpoint_{job_id}.tar"
        final_checkpoint_tar = f"{temp_dir}/redis-checkpoint_{job_id}.tar"
        build_dir = f"{temp_dir}/restore_tar_{job_id}"
        
        iter_names = [f"iter{i}_{job_id}" for i in range(1, pre_dumps_count + 1)]
        final_iter_name = f"iter_final_{job_id}"

        source_cleanup_paths = [
            dummy_checkpoint_tar,
            final_checkpoint_tar,
            build_dir,
            f"{temp_dir}/{final_iter_name}"
        ] + [f"{temp_dir}/{it}" for it in iter_names]

        target_cleanup_paths = [
            final_checkpoint_tar,
            f"{temp_dir}/pod-localhost_{job_id}.json",
            f"{temp_dir}/container-redis-restore_{job_id}.json"
        ]

        try:
            # === PASSO 1: Exportar metadados iniciais ===
            job.step = "EXPORTING_METADATA"
            logger.info(f"[{job_id[:8]}] Iniciando exportação de metadados...")
            container.state = ContainerState.CHECKPOINTING
            await self.cri_client.checkpoint_container(source_conn, container_id, dummy_checkpoint_tar)
            await source_conn.run(f"sudo chown {self.username}:{self.username} {dummy_checkpoint_tar}")

            # === PASSO 2: Realizar Pre-Dumps iterativos incrementais ===
            job.step = "PRE_DUMPING"
            for i in range(1, pre_dumps_count + 1):
                iter_name = f"iter{i}_{job_id}"
                image_path = f"{temp_dir}/{iter_name}"
                parent_path = None
                if i > 1:
                    # O parent-path deve ser um link relativo ao diretório atual da iteração
                    parent_path = f"../iter{i-1}_{job_id}"

                logger.info(f"[{job_id[:8]}] Executando pre-dump {i}/{pre_dumps_count}...")
                await self.runc_client.pre_dump(source_conn, container_id, image_path, parent_path)
                await source_conn.run(f"sudo chown -R {self.username}:{self.username} {image_path}")
            
            if pre_dumps_count > 0:
                container.state = ContainerState.PRE_DUMPED

            # === PASSO 3: Executar Checkpoint Final (Parada do container) ===
            job.step = "FINAL_CHECKPOINT"
            logger.info(f"[{job_id[:8]}] Executando checkpoint final (isso parará o contêiner original)...")
            
            final_image_path = f"{temp_dir}/{final_iter_name}"
            parent_path = f"../iter{pre_dumps_count}_{job_id}" if pre_dumps_count > 0 else None
            
            await self.runc_client.final_checkpoint(source_conn, container_id, final_image_path, parent_path)
            await source_conn.run(f"sudo chown -R {self.username}:{self.username} {final_image_path}")
            container.state = ContainerState.MIGRATING

            # === PASSO 4: Montar o Tarball Auto-Contido de Restauração ===
            job.step = "PREPARING_TARBALL"
            logger.info(f"[{job_id[:8]}] Consolidando tarball auto-contido no nó de origem...")
            
            await self.storage_manager.prepare_tarball(
                conn=source_conn,
                dummy_checkpoint_tar=dummy_checkpoint_tar,
                iter_names=iter_names,
                final_iter_name=final_iter_name,
                build_dir=build_dir,
                final_checkpoint_tar=final_checkpoint_tar,
                temp_dir=temp_dir
            )
            await source_conn.run(f"sudo chown {self.username}:{self.username} {final_checkpoint_tar}")

            # === PASSO 5: Transferência via Rsync para o Destino ===
            job.step = "TRANSFERRING"
            logger.info(f"[{job_id[:8]}] Transferindo tarball consolidado para o nó de destino {target_ip}...")
            
            target_tar_path = f"{temp_dir}/redis-checkpoint.tar" # Usamos o caminho fixo esperado no json de restore
            await self.storage_manager.transfer_tarball(
                source_conn=source_conn,
                source_tar_path=final_checkpoint_tar,
                target_ip=target_ip,
                target_tar_path=target_tar_path,
                private_key_content=self.private_key_content,
                username=self.username
            )

            # === PASSO 6: Preparar Configurações no Nó de Destino ===
            job.step = "PREPARING_TARGET_CONFIGS"
            logger.info(f"[{job_id[:8]}] Carregando configurações de Pod e Contêiner no nó de destino...")
            
            # Lê as configurações locais do coordenador
            with open(pod_config_local_path, "r") as f:
                pod_config_content = f.read()
            with open(container_restore_local_path, "r") as f:
                container_restore_content = f.read()

            target_pod_json_path = f"{temp_dir}/pod-localhost_{job_id}.json"
            target_container_json_path = f"{temp_dir}/container-redis-restore_{job_id}.json"

            # Escreve os arquivos JSON de configuração temporários no nó de destino
            await target_conn.run(f"echo '{pod_config_content}' > {target_pod_json_path}")
            await target_conn.run(f"echo '{container_restore_content}' > {target_container_json_path}")

            # === PASSO 7: Restaurar o Contêiner no Destino ===
            job.step = "RESTORING"
            logger.info(f"[{job_id[:8]}] Iniciando pod e contêiner restaurado no destino...")
            
            # Cria e roda o Pod sandbox
            new_pod_id = await self.cri_client.run_pod(target_conn, target_pod_json_path)
            logger.info(f"[{job_id[:8]}] Pod Sandbox criado no destino: {new_pod_id[:12]}")

            # Cria o container com base na imagem do tarball restaurado
            new_container_id = await self.cri_client.create_container(
                conn=target_conn,
                pod_id=new_pod_id,
                container_config=target_container_json_path,
                pod_config=target_pod_json_path
            )
            logger.info(f"[{job_id[:8]}] Contêiner criado a partir do checkpoint: {new_container_id[:12]}")

            # Inicia o container restaurado
            await self.cri_client.start_container(target_conn, new_container_id)
            logger.info(f"[{job_id[:8]}] Contêiner iniciado com sucesso!")

            # === PASSO 8: Limpeza de Recursos na Origem ===
            job.step = "CLEANING_SOURCE"
            logger.info(f"[{job_id[:8]}] Removendo pod e contêiner antigos no nó de origem...")
            
            # Remove container e pod no nó de origem
            await self.cri_client.remove_container(source_conn, container_id)
            await self.cri_client.stop_pod(source_conn, old_pod_id)
            await self.cri_client.remove_pod(source_conn, old_pod_id)

            # === PASSO 9: Atualização de Estados e Limpeza de Arquivos Temporários ===
            job.step = "FINALIZING"
            logger.info(f"[{job_id[:8]}] Executando limpezas finais de arquivos...")
            
            # Limpa arquivos temporários em paralelo nos dois nós
            await asyncio.gather(
                self.storage_manager.cleanup_paths(source_conn, source_cleanup_paths),
                self.storage_manager.cleanup_paths(target_conn, target_cleanup_paths)
            )

            # Atualiza o estado global em memória
            del source_node.containers[container_id]
            
            # Atualiza a lista do target
            await self.scan_node_containers(target_ip)

            job.status = "COMPLETED"
            job.step = "DONE"
            job.end_time = time.time()
            logger.info(f"[{job_id[:8]}] SUCESSO: Migração concluída em {job.end_time - job.start_time:.2f} segundos!")

        except Exception as e:
            job.status = "FAILED"
            job.error_msg = str(e)
            job.end_time = time.time()
            logger.error(f"[{job_id[:8]}] ERRO durante a migração: {e}")
            
            # Tenta realizar limpeza parcial mesmo em caso de falha
            try:
                await asyncio.gather(
                    self.storage_manager.cleanup_paths(source_conn, source_cleanup_paths),
                    self.storage_manager.cleanup_paths(target_conn, target_cleanup_paths),
                    return_exceptions=True
                )
            except Exception:
                pass
            
            # Atualiza a varredura para garantir consistência de estados reais
            await asyncio.gather(
                self.scan_node_containers(source_ip),
                self.scan_node_containers(target_ip),
                return_exceptions=True
            )

    async def start_container_on_node(
        self,
        node_ip: str,
        pod_config_path: str,
        container_config_path: str
    ) -> tuple[str, str]:
        """
        Inicia um Pod Sandbox e um Contêiner em um nó específico.
        Transfere os arquivos de configuração locais da controladora, puxa a imagem se necessário e roda crictl.
        """
        import json
        logger.info(f"Iniciando processo para rodar contêiner no nó {node_ip}...")
        
        # 1. Validações de conexão
        conn = self.connections.get(node_ip)
        node = self.nodes.get(node_ip)
        if not conn or not node or node.status != NodeStatus.ONLINE:
            raise RuntimeError(f"Nó {node_ip} não está ONLINE ou não possui conexão ativa.")

        # 2. Leitura dos arquivos de configuração locais
        if not os.path.exists(pod_config_path):
            raise FileNotFoundError(f"Arquivo de configuração do pod não encontrado: {pod_config_path}")
        if not os.path.exists(container_config_path):
            raise FileNotFoundError(f"Arquivo de configuração do contêiner não encontrado: {container_config_path}")

        with open(pod_config_path, "r") as f:
            pod_config_content = f.read()
        with open(container_config_path, "r") as f:
            container_config_content = f.read()

        # 3. Extração do nome do container e da imagem do container
        try:
            container_json = json.loads(container_config_content)
            image_name = container_json.get("image", {}).get("image", "")
            container_name = container_json.get("metadata", {}).get("name", "container-novo")
        except Exception as e:
            raise ValueError(f"Falha ao interpretar JSON do contêiner: {e}")

        logger.info(f"Configuração interpretada com sucesso. Nome: {container_name} | Imagem: {image_name}")

        # 4. Escrita dos arquivos temporários na máquina de destino
        remote_pod_path = f"/tmp/pod-config_{container_name}.json"
        remote_container_path = f"/tmp/container-config_{container_name}.json"

        # Note: Escapamos as aspas simples e o conteúdo para evitar quebra no shell bash
        escaped_pod_content = pod_config_content.replace("'", "'\\''")
        escaped_container_content = container_config_content.replace("'", "'\\''")

        logger.info(f"Escrevendo arquivos JSON no host de destino {node_ip}...")
        await conn.run(f"cat <<'EOF' > {remote_pod_path}\n{escaped_pod_content}\nEOF")
        await conn.run(f"cat <<'EOF' > {remote_container_path}\n{escaped_container_content}\nEOF")

        # 5. Download (pull) da imagem no nó de destino caso não exista localmente
        if image_name:
            # Verifica se a imagem já está presente no host
            check_res = await conn.run(f"sudo crictl images -q {image_name}")
            if check_res.exit_status == 0 and check_res.stdout.strip():
                logger.info(f"Imagem '{image_name}' já existe no nó {node_ip}. Pulando download (pull).")
            else:
                logger.info(f"Imagem '{image_name}' não encontrada no nó {node_ip}. Puxando imagem...")
                pull_res = await conn.run(f"sudo crictl pull {image_name}")
                if pull_res.exit_status != 0:
                    raise RuntimeError(f"Falha ao puxar a imagem {image_name} no nó {node_ip}. Stderr: {pull_res.stderr}")

        # 6. Execução do Pod Sandbox
        logger.info(f"Iniciando Pod Sandbox no nó {node_ip}...")
        pod_id = await self.cri_client.run_pod(conn, remote_pod_path)
        logger.info(f"Pod Sandbox criado com sucesso! ID: {pod_id}")

        # 7. Criação do Contêiner
        try:
            logger.info(f"Criando contêiner '{container_name}' no nó {node_ip}...")
            container_id = await self.cri_client.create_container(conn, pod_id, remote_container_path, remote_pod_path)
            logger.info(f"Contêiner criado com sucesso! ID: {container_id}")

            # 8. Inicialização do Contêiner
            logger.info(f"Iniciando contêiner '{container_name}' (ID: {container_id[:12]}) no nó {node_ip}...")
            await self.cri_client.start_container(conn, container_id)
            logger.info(f"Contêiner '{container_name}' iniciado com sucesso!")

            # Realiza novo scan no nó para atualizar a memória do daemon
            await self.scan_node_containers(node_ip)
            return container_id, pod_id

        except Exception as e:
            # Caso falhe a criação ou inicialização, tenta limpar o pod criado
            logger.error(f"Erro ao inicializar contêiner. Limpando pod sandbox {pod_id[:12]}...")
            try:
                await self.cri_client.stop_pod(conn, pod_id)
                await self.cri_client.remove_pod(conn, pod_id)
            except Exception as clean_err:
                logger.warning(f"Falha na limpeza do pod sandbox: {clean_err}")
            raise e

    async def start_interactive_migrate(
        self,
        container_id: str,
        source_ip: str,
        target_ip: str,
        pod_config_path: str = "/home/dev/files/pod-localhost.json",
        container_config_path: str = "/home/dev/files/container-redis-restore.json"
    ) -> str:
        """
        Inicializa uma sessão de migração interativa e exporta os metadados iniciais.
        """
        source_conn = self.connections.get(source_ip)
        target_conn = self.connections.get(target_ip)

        if not source_conn or not target_conn:
            raise RuntimeError(f"Conexões de origem ({source_ip}) ou destino ({target_ip}) não disponíveis.")

        # Verifica se o container existe na origem (suportando IDs curtos/prefixos)
        source_node = self.nodes.get(source_ip)
        found_id = None
        if source_node:
            for c_id in source_node.containers:
                if c_id.startswith(container_id):
                    found_id = c_id
                    break

        if not source_node or not found_id:
            raise RuntimeError(f"Contêiner {container_id[:12]} não encontrado no nó de origem {source_ip}.")

        container = source_node.containers[found_id]
        container_id = found_id
        
        job_id = str(uuid.uuid4())
        temp_dir = "/tmp"
        dummy_checkpoint_tar = f"{temp_dir}/dummy-checkpoint_{job_id}.tar"
        
        job = MigrationJob(
            job_id=job_id,
            container_id=container_id,
            source_ip=source_ip,
            target_ip=target_ip,
            status="IN_PROGRESS",
            step="INITIALIZING",
            start_time=time.time(),
            is_interactive=True,
            pod_config_local_path=pod_config_path,
            container_restore_local_path=container_config_path,
            dummy_checkpoint_tar=dummy_checkpoint_tar
        )
        self.jobs[job_id] = job
        
        logger.info(f"[{job_id[:8]}] [Interactive] Iniciando exportação de metadados...")
        container.state = ContainerState.CHECKPOINTING
        try:
            await self.cri_client.checkpoint_container(source_conn, container_id, dummy_checkpoint_tar)
            await source_conn.run(f"sudo chown {self.username}:{self.username} {dummy_checkpoint_tar}")
            job.step = "METADATA_EXPORTED"
            logger.info(f"[{job_id[:8]}] [Interactive] Metadados exportados com sucesso.")
        except Exception as e:
            job.status = "FAILED"
            job.error_msg = f"Erro no checkpoint de metadados: {e}"
            container.state = ContainerState.FAILED
            logger.error(job.error_msg)
            raise e
            
        return job_id

    async def pre_dump_interactive(self, job_id: str, transfer: bool) -> tuple[int, bool, str]:
        """
        Executa um pre-dump incremental e opcionalmente o transfere para o destino.
        """
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} não encontrado.")
            
        if job.status == "FAILED" or job.status == "COMPLETED":
            raise RuntimeError(f"O Job {job_id} já está no estado final {job.status}.")

        source_conn = self.connections.get(job.source_ip)
        if not source_conn:
            raise RuntimeError(f"Conexão de origem ({job.source_ip}) não disponível.")

        i = len(job.interactive_iterations) + 1
        iter_name = f"iter{i}_{job_id}"
        image_path = f"/tmp/{iter_name}"
        
        parent_path = None
        if i > 1:
            parent_path = f"../{job.interactive_iterations[-1]}"
            
        job.step = f"PRE_DUMPING_ITER_{i}"
        logger.info(f"[{job_id[:8]}] [Interactive] Executando pre-dump {i}...")
        
        await self.runc_client.pre_dump(source_conn, job.container_id, image_path, parent_path)
        await source_conn.run(f"sudo chown -R {self.username}:{self.username} {image_path}")
        job.interactive_iterations.append(iter_name)
        
        source_node = self.nodes.get(job.source_ip)
        if source_node and job.container_id in source_node.containers:
            source_node.containers[job.container_id].state = ContainerState.PRE_DUMPED

        transferred = False
        msg = f"Pre-dump {i} gerado com sucesso."
        
        if transfer:
            job.step = f"TRANSFERRING_ITER_{i}"
            logger.info(f"[{job_id[:8]}] [Interactive] Transferindo pre-dump {i} para {job.target_ip}...")
            
            target_path = f"/tmp/{iter_name}"
            target_conn = self.connections.get(job.target_ip)
            if not target_conn:
                raise RuntimeError(f"Conexão com destino ({job.target_ip}) indisponível para transferência.")
            await target_conn.run(f"sudo mkdir -p {target_path}")
            await target_conn.run(f"sudo chown -R {self.username}:{self.username} {target_path}")
            
            await self.storage_manager.transfer_path(
                source_conn=source_conn,
                source_path=image_path,
                target_ip=job.target_ip,
                target_path=target_path,
                private_key_content=self.private_key_content,
                username=self.username,
                is_dir=True
            )
            job.transferred_iterations.append(iter_name)
            transferred = True
            msg += f" Transferido para o nó {job.target_ip}."
            
        job.step = "READY_FOR_NEXT_STEP"
        return i, transferred, msg

    async def final_interactive_migrate(self, job_id: str) -> str:
        """
        Inicia em background a etapa final da migração interativa.
        """
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} não encontrado.")
            
        if job.status == "FAILED" or job.status == "COMPLETED":
            raise RuntimeError(f"O Job {job_id} já está no estado final {job.status}.")
            
        asyncio.create_task(
            self._execute_final_migration_workflow(job_id)
        )
        return job_id

    async def _execute_final_migration_workflow(self, job_id: str) -> None:
        job = self.jobs[job_id]
        job.status = "IN_PROGRESS"
        
        source_conn = self.connections.get(job.source_ip)
        target_conn = self.connections.get(job.target_ip)
        
        if not source_conn or not target_conn:
            job.status = "FAILED"
            job.error_msg = f"Conexões de origem ({job.source_ip}) ou destino ({job.target_ip}) não disponíveis."
            logger.error(job.error_msg)
            return

        try:
            # 1. Sincroniza qualquer pre-dump que ainda não tenha sido transferido
            job.step = "SYNCING_UNTRANSFERRED_DRAINS"
            logger.info(f"[{job_id[:8]}] [Interactive] Verificando pre-dumps não transferidos...")
            
            for iter_name in job.interactive_iterations:
                if iter_name not in job.transferred_iterations:
                    logger.info(f"[{job_id[:8]}] [Interactive] Sincronizando pre-dump {iter_name} ausente no destino...")
                    image_path = f"/tmp/{iter_name}"
                    target_path = f"/tmp/{iter_name}"
                    
                    await source_conn.run(f"sudo chown -R {self.username}:{self.username} {image_path}")
                    await target_conn.run(f"sudo mkdir -p {target_path}")
                    await target_conn.run(f"sudo chown -R {self.username}:{self.username} {target_path}")
                    await self.storage_manager.transfer_path(
                        source_conn=source_conn,
                        source_path=image_path,
                        target_ip=job.target_ip,
                        target_path=target_path,
                        private_key_content=self.private_key_content,
                        username=self.username,
                        is_dir=True
                    )
                    job.transferred_iterations.append(iter_name)

            # 2. Executa o Checkpoint Final (Parada do container) na origem
            job.step = "FINAL_CHECKPOINT"
            logger.info(f"[{job_id[:8]}] [Interactive] Executando checkpoint final na origem...")
            
            final_iter_name = f"iter_final_{job_id}"
            final_image_path = f"/tmp/{final_iter_name}"
            
            parent_path = f"../{job.interactive_iterations[-1]}" if job.interactive_iterations else None
            
            source_node = self.nodes.get(job.source_ip)
            if source_node and job.container_id in source_node.containers:
                source_node.containers[job.container_id].state = ContainerState.MIGRATING
                
            await self.runc_client.final_checkpoint(source_conn, job.container_id, final_image_path, parent_path)
            await source_conn.run(f"sudo chown -R {self.username}:{self.username} {final_image_path}")

            # 3. Transfere o dump final e o dummy metadata para o destino
            job.step = "TRANSFERRING_FINAL_DUMP"
            logger.info(f"[{job_id[:8]}] [Interactive] Transferindo checkpoint final e metadados para o destino {job.target_ip}...")
            
            target_final_path = f"/tmp/{final_iter_name}"
            await target_conn.run(f"sudo mkdir -p {target_final_path}")
            await target_conn.run(f"sudo chown -R {self.username}:{self.username} {target_final_path}")
            await self.storage_manager.transfer_path(
                source_conn=source_conn,
                source_path=final_image_path,
                target_ip=job.target_ip,
                target_path=target_final_path,
                private_key_content=self.private_key_content,
                username=self.username,
                is_dir=True
            )
            
            target_dummy_tar = f"/tmp/dummy-checkpoint_{job_id}.tar"
            await source_conn.run(f"sudo chown {self.username}:{self.username} {job.dummy_checkpoint_tar}")
            await self.storage_manager.transfer_path(
                source_conn=source_conn,
                source_path=job.dummy_checkpoint_tar,
                target_ip=job.target_ip,
                target_path=target_dummy_tar,
                private_key_content=self.private_key_content,
                username=self.username,
                is_dir=False
            )

            # 4. Consolidar o Tarball diretamente no nó de destino B
            job.step = "PREPARING_TARBALL"
            logger.info(f"[{job_id[:8]}] [Interactive] Consolidando tarball de restauração no destino {job.target_ip}...")
            
            build_dir = f"/tmp/restore_tar_{job_id}"
            target_tar_path = f"/tmp/redis-checkpoint.tar"
            
            await self.storage_manager.prepare_tarball(
                conn=target_conn,
                dummy_checkpoint_tar=target_dummy_tar,
                iter_names=job.interactive_iterations,
                final_iter_name=final_iter_name,
                build_dir=build_dir,
                final_checkpoint_tar=target_tar_path,
                temp_dir="/tmp"
            )

            # 5. Carregar configurações locais de Pod/Container no nó de destino
            job.step = "PREPARING_TARGET_CONFIGS"
            logger.info(f"[{job_id[:8]}] [Interactive] Gravando arquivos JSON de configuração no destino...")
            
            with open(job.pod_config_local_path, "r") as f:
                pod_config_content = f.read()
            with open(job.container_restore_local_path, "r") as f:
                container_restore_content = f.read()
                
            target_pod_json_path = f"/tmp/pod-localhost_{job_id}.json"
            target_container_json_path = f"/tmp/container-redis-restore_{job_id}.json"
            
            await target_conn.run(f"echo '{pod_config_content}' > {target_pod_json_path}")
            await target_conn.run(f"echo '{container_restore_content}' > {target_container_json_path}")

            # 6. Restaurar o Contêiner no destino B
            job.step = "RESTORING"
            logger.info(f"[{job_id[:8]}] [Interactive] Iniciando restauração do pod sandbox no destino...")
            
            new_pod_id = await self.cri_client.run_pod(target_conn, target_pod_json_path)
            logger.info(f"[{job_id[:8]}] [Interactive] Pod Sandbox criado: {new_pod_id[:12]}")
            
            new_container_id = await self.cri_client.create_container(
                conn=target_conn,
                pod_id=new_pod_id,
                container_config=target_container_json_path,
                pod_config=target_pod_json_path
            )
            logger.info(f"[{job_id[:8]}] [Interactive] Contêiner criado: {new_container_id[:12]}")
            
            await self.cri_client.start_container(target_conn, new_container_id)
            logger.info(f"[{job_id[:8]}] [Interactive] Contêiner iniciado no destino!")

            # 7. Limpeza de Recursos na Origem
            job.step = "CLEANING_SOURCE"
            logger.info(f"[{job_id[:8]}] [Interactive] Removendo pod/container antigo na origem...")
            
            old_pod_id = None
            if source_node and job.container_id in source_node.containers:
                old_pod_id = source_node.containers[job.container_id].pod_id
                
            await self.cri_client.remove_container(source_conn, job.container_id)
            if old_pod_id:
                await self.cri_client.stop_pod(source_conn, old_pod_id)
                await self.cri_client.remove_pod(source_conn, old_pod_id)

            # 8. Limpeza de Arquivos Temporários em ambas as máquinas
            job.step = "FINALIZING"
            logger.info(f"[{job_id[:8]}] [Interactive] Removendo arquivos e pastas temporárias...")
            
            source_cleanup = [
                job.dummy_checkpoint_tar,
                final_image_path,
            ] + [f"/tmp/{it}" for it in job.interactive_iterations]
            
            target_cleanup = [
                target_dummy_tar,
                target_final_path,
                build_dir,
                target_pod_json_path,
                target_container_json_path,
                target_tar_path
            ] + [f"/tmp/{it}" for it in job.interactive_iterations]
            
            await asyncio.gather(
                self.storage_manager.cleanup_paths(source_conn, source_cleanup),
                self.storage_manager.cleanup_paths(target_conn, target_cleanup),
                return_exceptions=True
            )
            
            if source_node and job.container_id in source_node.containers:
                del source_node.containers[job.container_id]
                
            await self.scan_node_containers(job.target_ip)
            
            job.status = "COMPLETED"
            job.step = "DONE"
            job.end_time = time.time()
            logger.info(f"[{job_id[:8]}] [Interactive] SUCESSO: Migração interativa concluída em {job.end_time - job.start_time:.2f}s!")

        except Exception as e:
            job.status = "FAILED"
            job.error_msg = str(e)
            job.end_time = time.time()
            logger.error(f"[{job_id[:8]}] [Interactive] ERRO durante a migração final: {e}")
            
            try:
                source_cleanup = [job.dummy_checkpoint_tar, final_image_path] + [f"/tmp/{it}" for it in job.interactive_iterations]
                target_cleanup = [target_dummy_tar, target_final_path, build_dir] + [f"/tmp/{it}" for it in job.interactive_iterations]
                await asyncio.gather(
                    self.storage_manager.cleanup_paths(source_conn, source_cleanup),
                    self.storage_manager.cleanup_paths(target_conn, target_cleanup),
                    return_exceptions=True
                )
            except Exception:
                pass
                
            await asyncio.gather(
                self.scan_node_containers(job.source_ip),
                self.scan_node_containers(job.target_ip),
                return_exceptions=True
            )

