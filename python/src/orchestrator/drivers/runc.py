import logging
from typing import Optional

logger = logging.getLogger(__name__)

class RuncClient:
    """
    Cliente para interagir com o runc CLI executando os checkpoints e pre-dumps
    necessários para a migração incremental iterativa.
    """
    def __init__(self, runc_root: str = "/run/runc"):
        self.runc_root = runc_root

    async def _run_cmd(self, conn, cmd: str) -> str:
        """Executa comandos via SSH de forma assíncrona."""
        logger.debug(f"Runc executando: {cmd}")
        result = await conn.run(f"sudo {cmd}")
        if result.exit_status != 0:
            stderr = result.stderr.strip() if result.stderr else "Sem saída de erro"
            stdout = result.stdout.strip() if result.stdout else "Sem saída padrão"
            raise RuntimeError(f"Runc falhou [{result.exit_status}]: {cmd}. Stdout: {stdout}. Stderr: {stderr}")
        return result.stdout.strip() if result.stdout else ""

    async def pre_dump(self, conn, container_id: str, image_path: str, parent_path: Optional[str] = None) -> None:
        """
        Executa um checkpoint --pre-dump do container. A memória é copiada de forma
        incremental e o contêiner continua em execução.
        """
        # Ex: runc --root /run/runc checkpoint --pre-dump --image-path /tmp/iter1 CONTAINER_ID
        cmd = f"runc --root {self.runc_root} checkpoint --pre-dump --image-path {image_path}"
        if parent_path:
            # Ex: runc --root /run/runc checkpoint --pre-dump --parent-path ../iter1 --image-path /tmp/iter2 CONTAINER_ID
            cmd += f" --parent-path {parent_path}"
        cmd += f" {container_id}"
        
        logger.info(f"Executando pre-dump para {container_id[:12]} em {image_path} (parent: {parent_path})")
        await self._run_cmd(conn, f"mkdir -p {image_path}")
        await self._run_cmd(conn, cmd)

    async def final_checkpoint(self, conn, container_id: str, image_path: str, parent_path: Optional[str] = None) -> None:
        """
        Executa o checkpoint final do container, parando o processo original.
        A memória restante é salva no local indicado.
        """
        # Ex: runc --root /run/runc checkpoint --parent-path ../iter2 --image-path /tmp/iter_final CONTAINER_ID
        cmd = f"runc --root {self.runc_root} checkpoint"
        if parent_path:
            cmd += f" --parent-path {parent_path}"
        cmd += f" --image-path {image_path} {container_id}"
        
        logger.info(f"Executando checkpoint final para {container_id[:12]} em {image_path} (parent: {parent_path})")
        await self._run_cmd(conn, f"mkdir -p {image_path}")
        await self._run_cmd(conn, cmd)
