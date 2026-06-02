import json
import logging
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from orchestrator.models import Container, ContainerState, NodeStatus

logger = logging.getLogger(__name__)

class CRIClientInterface(ABC):
    """
    Interface abstrata para controle do CRI-O.
    Permite implementações via CLI (crictl) e gRPC.
    """
    @abstractmethod
    async def list_containers(self, conn) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def list_pods(self, conn) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def run_pod(self, conn, pod_config: str) -> str:
        pass

    @abstractmethod
    async def create_container(self, conn, pod_id: str, container_config: str, pod_config: str) -> str:
        pass

    @abstractmethod
    async def start_container(self, conn, container_id: str) -> None:
        pass

    @abstractmethod
    async def stop_container(self, conn, container_id: str) -> None:
        pass

    @abstractmethod
    async def remove_container(self, conn, container_id: str) -> None:
        pass

    @abstractmethod
    async def stop_pod(self, conn, pod_id: str) -> None:
        pass

    @abstractmethod
    async def remove_pod(self, conn, pod_id: str) -> None:
        pass

    @abstractmethod
    async def checkpoint_container(self, conn, container_id: str, export_path: str) -> None:
        pass

    @abstractmethod
    async def exec_command(self, conn, container_id: str, cmd: List[str]) -> str:
        pass


class CRICliClient(CRIClientInterface):
    """
    Implementação do cliente CRI utilizando o binário crictl sobre SSH (asyncssh).
    O crictl executa chamadas gRPC locais sob o capô, tornando esta abordagem
    altamente estável, nativa e livre de dependências extras de compilação.
    """
    
    async def _run_cmd(self, conn, cmd: str) -> str:
        """Helper para rodar comando sudo assincronamente via SSH."""
        logger.debug(f"Executando no host: {cmd}")
        result = await conn.run(f"sudo {cmd}")
        if result.exit_status != 0:
            stderr = result.stderr.strip() if result.stderr else "Sem saída de erro"
            stdout = result.stdout.strip() if result.stdout else "Sem saída padrão"
            raise RuntimeError(f"Comando falhou [{result.exit_status}]: {cmd}. Stdout: {stdout}. Stderr: {stderr}")
        return result.stdout.strip() if result.stdout else ""

    async def list_containers(self, conn) -> List[Dict[str, Any]]:
        try:
            output = await self._run_cmd(conn, "crictl ps -a -o json")
            if not output:
                return []
            data = json.loads(output)
            return data.get("containers", [])
        except Exception as e:
            logger.error(f"Erro ao listar contêineres: {e}")
            raise

    async def list_pods(self, conn) -> List[Dict[str, Any]]:
        try:
            output = await self._run_cmd(conn, "crictl pods -o json")
            if not output:
                return []
            data = json.loads(output)
            return data.get("items", [])
        except Exception as e:
            logger.error(f"Erro ao listar pods: {e}")
            raise

    async def run_pod(self, conn, pod_config: str) -> str:
        # pod_config pode ser o caminho para o arquivo json
        output = await self._run_cmd(conn, f"crictl runp {pod_config}")
        return output.strip()

    async def create_container(self, conn, pod_id: str, container_config: str, pod_config: str) -> str:
        output = await self._run_cmd(conn, f"crictl create {pod_id} {container_config} {pod_config}")
        return output.strip()

    async def start_container(self, conn, container_id: str) -> None:
        await self._run_cmd(conn, f"crictl start {container_id}")

    async def stop_container(self, conn, container_id: str) -> None:
        await self._run_cmd(conn, f"crictl stop {container_id}")

    async def remove_container(self, conn, container_id: str) -> None:
        await self._run_cmd(conn, f"crictl rm {container_id}")

    async def stop_pod(self, conn, pod_id: str) -> None:
        await self._run_cmd(conn, f"crictl stopp {pod_id}")

    async def remove_pod(self, conn, pod_id: str) -> None:
        await self._run_cmd(conn, f"crictl rmp {pod_id}")

    async def checkpoint_container(self, conn, container_id: str, export_path: str) -> None:
        # Comando correspondente à Fase 3, Passo 5 do guia (crictl checkpoint)
        await self._run_cmd(conn, f"crictl checkpoint --export {export_path} {container_id}")

    async def exec_command(self, conn, container_id: str, cmd: List[str]) -> str:
        cmd_str = " ".join(cmd)
        output = await self._run_cmd(conn, f"crictl exec {container_id} {cmd_str}")
        return output


class CRIGrpcClient(CRIClientInterface):
    """
    Cliente CRI utilizando chamada gRPC pura.
    Mapeia o socket gRPC /var/run/crio/crio.sock remotamente através de um túnel SSH do asyncssh.
    Caso o módulo grpc ou os stubs de protobuf cri-api não estejam disponíveis,
    deve lançar ImportError para fazer fallback automático.
    """
    def __init__(self):
        # Tentamos importar os módulos necessários
        try:
            import grpc
            self.grpc = grpc
            # Importar os stubs gerados localmente (se compilados)
            # Para manter modularidade, tentamos carregar do caminho python/generated
            import sys
            sys.path.append(os.path.join(os.path.dirname(__file__), 'generated'))
            import api_pb2
            import api_pb2_grpc
            self.api_pb2 = api_pb2
            self.api_pb2_grpc = api_pb2_grpc
            self.available = True
        except ImportError:
            self.available = False
            logger.warning("gRPC do CRI-O ou stubs de Protobuf não disponíveis. gRPC client desabilitado.")

    def is_available(self) -> bool:
        return self.available

    async def _get_channel(self, conn, local_sock_path: str = "/tmp/crio_local.sock"):
        """Estabelece o túnel do socket UNIX sobre SSH e retorna o canal gRPC assíncrono."""
        if not self.available:
            raise RuntimeError("gRPC Client não está disponível no ambiente.")
        
        # Remove socket local anterior se existir
        if os.path.exists(local_sock_path):
            os.remove(local_sock_path)

        # Mapeamento do UDS através do asyncssh
        # Note: Esta é uma chamada conceitual pois necessita do túnel ativo no contexto async.
        # Na prática, gerenciaremos o túnel no ciclo de vida do MigrationManager.
        self.channel = self.grpc.aio.insecure_channel(f"unix://{local_sock_path}")
        self.stub = self.api_pb2_grpc.RuntimeServiceStub(self.channel)
        return self.stub

    # Implementações dos métodos gRPC utilizando o stub
    async def list_containers(self, conn) -> List[Dict[str, Any]]:
        # Exemplo simplificado de implementação gRPC:
        # stub = await self._get_channel(conn)
        # response = await stub.ListContainers(self.api_pb2.ListContainersRequest())
        # Parse response...
        raise NotImplementedError("Utilizando CRICliClient de fallback estável. gRPC nativo requer stubs compilados.")

    async def list_pods(self, conn) -> List[Dict[str, Any]]:
        raise NotImplementedError("Utilizando CRICliClient de fallback estável.")

    async def run_pod(self, conn, pod_config: str) -> str:
        raise NotImplementedError("Utilizando CRICliClient de fallback estável.")

    async def create_container(self, conn, pod_id: str, container_config: str, pod_config: str) -> str:
        raise NotImplementedError("Utilizando CRICliClient de fallback estável.")

    async def start_container(self, conn, container_id: str) -> None:
        raise NotImplementedError("Utilizando CRICliClient de fallback estável.")

    async def stop_container(self, conn, container_id: str) -> None:
        raise NotImplementedError("Utilizando CRICliClient de fallback estável.")

    async def remove_container(self, conn, container_id: str) -> None:
        raise NotImplementedError("Utilizando CRICliClient de fallback estável.")

    async def stop_pod(self, conn, pod_id: str) -> None:
        raise NotImplementedError("Utilizando CRICliClient de fallback estável.")

    async def remove_pod(self, conn, pod_id: str) -> None:
        raise NotImplementedError("Utilizando CRICliClient de fallback estável.")

    async def checkpoint_container(self, conn, container_id: str, export_path: str) -> None:
        raise NotImplementedError("Utilizando CRICliClient de fallback estável.")

    async def exec_command(self, conn, container_id: str, cmd: List[str]) -> str:
        raise NotImplementedError("Utilizando CRICliClient de fallback estável.")
