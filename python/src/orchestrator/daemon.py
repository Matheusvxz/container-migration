#!/usr/bin/env python3
import asyncio
import argparse
import sys
import os
import logging
from concurrent import futures

import grpc

script_dir = os.path.dirname(os.path.abspath(__file__))

# Tenta carregar os stubs. Se não existirem, avisa que é necessário compilar
try:
    from orchestrator.proto import migration_pb2
    from orchestrator.proto import migration_pb2_grpc
except ImportError:
    print("ERRO: Os stubs gRPC não foram encontrados. Por favor, execute compile_proto.py primeiro.", file=sys.stderr)
    sys.exit(1)

from orchestrator.core.migration import MigrationManager
from orchestrator.models import NodeStatus, ContainerState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("migration_daemon")


class MigrationServiceServicer(migration_pb2_grpc.MigrationServiceServicer):
    """Implementa o serviço gRPC expondo o MigrationManager."""
    def __init__(self, manager: MigrationManager):
        self.manager = manager

    async def ListNodes(self, request, context):
        logger.info("Recebida chamada ListNodes")
        response = migration_pb2.NodeListResponse()
        
        for ip, node in self.manager.nodes.items():
            node_info = migration_pb2.NodeInfo(
                ip=ip,
                status=node.status.value,
                error_msg=node.error_msg or ""
            )
            
            for c_id, container in node.containers.items():
                c_info = migration_pb2.ContainerInfo(
                    id=container.id,
                    name=container.name,
                    pod_id=container.pod_id,
                    state=container.state.value,
                    image=container.image
                )
                node_info.containers.append(c_info)
                
            response.nodes.append(node_info)
            
        return response

    async def MigrateContainer(self, request, context):
        logger.info(f"Recebida chamada MigrateContainer: container={request.container_id[:12]}, de {request.source_ip} para {request.target_ip}")
        try:
            job_id = await self.manager.migrate_container(
                container_id=request.container_id,
                source_ip=request.source_ip,
                target_ip=request.target_ip,
                pre_dumps_count=request.pre_dumps_count
            )
            return migration_pb2.MigrateResponse(job_id=job_id)
        except Exception as e:
            logger.error(f"Erro ao disparar migração: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return migration_pb2.MigrateResponse()

    async def StartInteractiveMigrate(self, request, context):
        logger.info(f"Recebida chamada StartInteractiveMigrate: container={request.container_id[:12]}, de {request.source_ip} para {request.target_ip}")
        try:
            pod_cfg = request.pod_config_path if request.pod_config_path else "/home/dev/files/pod-localhost.json"
            cont_cfg = request.container_config_path if request.container_config_path else "/home/dev/files/container-redis-restore.json"
            
            job_id = await self.manager.start_interactive_migrate(
                container_id=request.container_id,
                source_ip=request.source_ip,
                target_ip=request.target_ip,
                pod_config_path=pod_cfg,
                container_config_path=cont_cfg
            )
            return migration_pb2.StartInteractiveMigrateResponse(job_id=job_id, message="Sessão de migração interativa iniciada.")
        except Exception as e:
            logger.error(f"Erro ao iniciar migração interativa: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return migration_pb2.StartInteractiveMigrateResponse()

    async def PreDumpInteractive(self, request, context):
        logger.info(f"Recebida chamada PreDumpInteractive: job_id={request.job_id[:8]}, transfer={request.transfer}")
        try:
            iteration, transferred, message = await self.manager.pre_dump_interactive(
                job_id=request.job_id,
                transfer=request.transfer
            )
            return migration_pb2.PreDumpInteractiveResponse(
                job_id=request.job_id,
                iteration=iteration,
                transferred=transferred,
                message=message
            )
        except Exception as e:
            logger.error(f"Erro no pre-dump interativo: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return migration_pb2.PreDumpInteractiveResponse()

    async def FinalInteractiveMigrate(self, request, context):
        logger.info(f"Recebida chamada FinalInteractiveMigrate: job_id={request.job_id[:8]}")
        try:
            job_id = await self.manager.final_interactive_migrate(
                job_id=request.job_id
            )
            return migration_pb2.FinalInteractiveMigrateResponse(
                job_id=job_id,
                message="Fase final de migração interativa iniciada no background."
            )
        except Exception as e:
            logger.error(f"Erro ao finalizar migração interativa: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return migration_pb2.FinalInteractiveMigrateResponse()


    async def GetJobStatus(self, request, context):
        job_id = request.job_id
        job = self.manager.jobs.get(job_id)
        if not job:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"Job {job_id} não encontrado.")
            return migration_pb2.JobStatusResponse()
            
        return migration_pb2.JobStatusResponse(
            job_id=job.job_id,
            container_id=job.container_id,
            source_ip=job.source_ip,
            target_ip=job.target_ip,
            status=job.status,
            step=job.step,
            start_time=job.start_time,
            end_time=job.end_time or 0.0,
            error_msg=job.error_msg or ""
        )

    async def ListJobs(self, request, context):
        response = migration_pb2.JobListResponse()
        for job in self.manager.jobs.values():
            j_resp = migration_pb2.JobStatusResponse(
                job_id=job.job_id,
                container_id=job.container_id,
                source_ip=job.source_ip,
                target_ip=job.target_ip,
                status=job.status,
                step=job.step,
                start_time=job.start_time,
                end_time=job.end_time or 0.0,
                error_msg=job.error_msg or ""
            )
            response.jobs.append(j_resp)
        return response

    async def Refresh(self, request, context):
        logger.info("Forçando varredura e scan nos hosts...")
        tasks = [
            self.manager.scan_node_containers(ip) 
            for ip, n in self.manager.nodes.items() 
            if n.status == NodeStatus.ONLINE
        ]
        if tasks:
            await asyncio.gather(*tasks)
        return migration_pb2.Empty()

    async def StartContainer(self, request, context):
        logger.info(f"Recebida chamada StartContainer: node={request.node_ip}, pod_config={request.pod_config_path}, container_config={request.container_config_path}")
        try:
            container_id, pod_id = await self.manager.start_container_on_node(
                node_ip=request.node_ip,
                pod_config_path=request.pod_config_path,
                container_config_path=request.container_config_path
            )
            return migration_pb2.StartContainerResponse(
                container_id=container_id,
                pod_id=pod_id,
                message="Contêiner e Pod iniciados com sucesso!"
            )
        except Exception as e:
            logger.error(f"Erro ao iniciar contêiner no nó: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return migration_pb2.StartContainerResponse()

    async def AddNode(self, request, context):
        ip = request.ip.strip()
        logger.info(f"Recebida chamada AddNode para o IP: {ip}")
        if not ip:
            return migration_pb2.AddNodeResponse(success=False, message="IP inválido ou vazio.")
        try:
            await self.manager.add_dynamic_node(ip)
            node = self.manager.nodes.get(ip)
            status_str = node.status.value if node else "UNKNOWN"
            msg = f"Nó {ip} adicionado com sucesso! Status atual: {status_str}"
            if node and node.error_msg:
                msg += f" (Erro: {node.error_msg})"
            return migration_pb2.AddNodeResponse(success=True, message=msg)
        except Exception as e:
            logger.error(f"Erro ao adicionar nó dinamicamente: {e}")
            return migration_pb2.AddNodeResponse(success=False, message=str(e))

    async def RemoveNode(self, request, context):
        ip = request.ip.strip()
        logger.info(f"Recebida chamada RemoveNode para o IP: {ip}")
        if not ip:
            return migration_pb2.RemoveNodeResponse(success=False, message="IP inválido ou vazio.")
        try:
            if ip not in self.manager.nodes:
                return migration_pb2.RemoveNodeResponse(success=False, message=f"Nó {ip} não está monitorado.")
            await self.manager.remove_dynamic_node(ip)
            return migration_pb2.RemoveNodeResponse(success=True, message=f"Nó {ip} removido com sucesso!")
        except Exception as e:
            logger.error(f"Erro ao remover nó dinamicamente: {e}")
            return migration_pb2.RemoveNodeResponse(success=False, message=str(e))

    async def SetNodes(self, request, context):
        ips = [ip.strip() for ip in request.ips if ip.strip()]
        logger.info(f"Recebida chamada SetNodes com os IPs: {ips}")
        try:
            await self.manager.set_dynamic_nodes(ips)
            return migration_pb2.SetNodesResponse(success=True, message=f"Lista de nós atualizada com sucesso! Total: {len(self.manager.nodes)} nós.")
        except Exception as e:
            logger.error(f"Erro ao definir nós dinamicamente: {e}")
            return migration_pb2.SetNodesResponse(success=False, message=str(e))


def read_hosts(file_path: str) -> list:
    """Lê a lista de IPs de nós de um arquivo de texto."""
    if not os.path.exists(file_path):
        logger.warning(f"Arquivo de hosts '{file_path}' não encontrado.")
        return []
    
    ips = []
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            ips.append(line)
    return ips


async def serve():
    parser = argparse.ArgumentParser(description="Daemon gRPC de Orquestração de Migração de Contêineres")
    parser.add_argument("-p", "--port", type=int, default=50051, help="Porta gRPC para escutar (padrão: 50051)")
    parser.add_argument("-k", "--key-path", default="../secrets/key", help="Caminho para chave privada SSH")
    parser.add_argument("-u", "--user", default="dev", help="Usuário SSH padrão")
    parser.add_argument("-i", "--hosts-file", default="hosts.txt", help="Caminho para o arquivo de hosts")
    args = parser.parse_args()

    # Corrige os caminhos para o diretório de instalação se necessário
    hosts_path = args.hosts_file if os.path.isabs(args.hosts_file) else os.path.join(script_dir, args.hosts_file)
    key_path = args.key_path if os.path.isabs(args.key_path) else os.path.join(script_dir, args.key_path)

    logger.info("=== Inicializando Daemon de Migração ===")
    logger.info(f"Escutando na porta: {args.port}")
    logger.info(f"Lendo hosts de: {hosts_path}")
    logger.info(f"Usando chave SSH: {key_path}")

    # Carrega IPs e inicializa o MigrationManager
    ips = read_hosts(hosts_path)
    if not ips:
        logger.error(f"Erro: Nenhum host ativo configurado em {hosts_path}. O Daemon necessita de pelo menos um nó.")
        sys.exit(1)

    manager = MigrationManager(key_path=key_path, username=args.user, hosts_file=hosts_path)
    
    # Faz a conexão concorrente e scan inicial de todos os hosts no startup
    logger.info("Estabelecendo conexão inicial com os nós...")
    await manager.initialize_connections(ips)

    # Inicializa o servidor gRPC
    # Note: Utilizamos a API do gRPC assíncrono nativo do Python (grpc.aio)
    server = grpc.aio.server()
    migration_pb2_grpc.add_MigrationServiceServicer_to_server(
        MigrationServiceServicer(manager), server
    )
    
    listen_addr = f"[::]:{args.port}"
    server.add_insecure_port(listen_addr)
    logger.info(f"Servidor gRPC iniciado em {listen_addr}")
    
    await server.start()
    
    try:
        # Mantém o loop assíncrono ativo rodando o servidor
        await server.wait_for_termination()
    except asyncio.CancelledError:
        logger.info("Finalizando Daemon...")
    finally:
        await server.stop(5)
        await manager.close_connections()
        logger.info("Daemon encerrado com sucesso.")

def main():
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        logger.info("Servidor interrompido manualmente.")

if __name__ == "__main__":
    main()
