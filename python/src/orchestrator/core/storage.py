import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

class StorageManager:
    """
    Gerencia arquivos, diretórios, montagem de tarballs consolidados e
    transferência de checkpoints entre nós de forma assíncrona.
    """

    async def _run_cmd(self, conn, cmd: str) -> str:
        """Helper para executar comandos via SSH de forma assíncrona."""
        result = await conn.run(f"sudo {cmd}")
        if result.exit_status != 0:
            stderr = result.stderr.strip() if result.stderr else "Sem saída de erro"
            stdout = result.stdout.strip() if result.stdout else "Sem saída padrão"
            raise RuntimeError(f"Storage falhou [{result.exit_status}]: {cmd}. Stdout: {stdout}. Stderr: {stderr}")
        return result.stdout.strip() if result.stdout else ""

    async def cleanup_paths(self, conn, paths: List[str]) -> None:
        """Limpa caminhos de arquivos/diretórios temporários no host."""
        if not paths:
            return
        paths_str = " ".join(paths)
        logger.info(f"Limpando caminhos temporários: {paths_str}")
        await self._run_cmd(conn, f"rm -rf {paths_str}")

    async def prepare_tarball(
        self,
        conn,
        dummy_checkpoint_tar: str,
        iter_names: List[str],
        final_iter_name: str,
        build_dir: str,
        final_checkpoint_tar: str,
        temp_dir: str = "/tmp"
    ) -> None:
        """
        Monta a estrutura auto-contida e gera o Tarball consolidado para restauração.
        Replica a lógica da Fase 3 do guia:
        1. Extrai o dummy-checkpoint.tar no build_dir.
        2. Substitui o diretório 'checkpoint' original pelo 'iter_final'.
        3. Copia todas as iterações anteriores de memória (iter1, iter2, etc.) para o build_dir.
        4. Corrige os links simbólicos de parentesco de forma relativa interna.
        5. Gera o tarball consolidado.
        """
        logger.info(f"Iniciando preparação do tarball em {build_dir}")

        # 1. Limpa e cria o diretório de build
        await self._run_cmd(conn, f"rm -rf {build_dir} && mkdir -p {build_dir}")
        
        # Extrai os metadados
        await self._run_cmd(conn, f"tar -C {build_dir} -xf {dummy_checkpoint_tar}")
        await self._run_cmd(conn, f"rm -rf {build_dir}/checkpoint")

        # 2. Copia o checkpoint final
        await self._run_cmd(conn, f"cp -a {temp_dir}/{final_iter_name} {build_dir}/checkpoint")

        # 3. Copia as iterações anteriores
        for iter_name in iter_names:
            await self._run_cmd(conn, f"cp -a {temp_dir}/{iter_name} {build_dir}/{iter_name}")

        # 4. Corrige os links simbólicos de parentesco relativos internos
        # checkpoint/parent -> ../<ultima_iteracao>
        if iter_names:
            last_iter = iter_names[-1]
            await self._run_cmd(conn, f"rm -f {build_dir}/checkpoint/parent")
            await self._run_cmd(conn, f"ln -s ../{last_iter} {build_dir}/checkpoint/parent")

            # Corrige as iterações anteriores em cascata: iter_N/parent -> ../iter_N-1
            for i in range(len(iter_names) - 1, 0, -1):
                curr_iter = iter_names[i]
                prev_iter = iter_names[i-1]
                await self._run_cmd(conn, f"rm -f {build_dir}/{curr_iter}/parent")
                await self._run_cmd(conn, f"ln -s ../{prev_iter} {build_dir}/{curr_iter}/parent")

        # 5. Gera o tarball consolidado pronto para o crictl
        # Como o tar precisa de mudança de diretório, envelopamos em um script shell inline
        tar_cmd = f'sh -c "cd {build_dir} && tar -cf {final_checkpoint_tar} *"'
        await self._run_cmd(conn, tar_cmd)
        logger.info(f"Tarball auto-contido gerado com sucesso em {final_checkpoint_tar}")

    async def transfer_tarball(
        self,
        source_conn,
        source_tar_path: str,
        target_ip: str,
        target_tar_path: str,
        private_key_content: str,
        username: str = "dev"
    ) -> None:
        """
        Transfere o arquivo tar consolidado do nó de origem diretamente para o nó de destino via rsync.
        Para autenticar, grava temporariamente a chave privada SSH na pasta /tmp do nó de origem,
        executa o rsync e em seguida remove a chave de forma segura para garantir proteção.
        """
        temp_key_path = "/tmp/migration_transfer_key"
        logger.info(f"Transferindo tarball do host de origem para {target_ip}:{target_tar_path}")

        try:
            # 1. Grava a chave privada temporariamente no nó de origem
            # Escapa o conteúdo da chave para gravação via comando de eco seguro
            escaped_key = private_key_content.replace('"', '\\"').replace('$', '\\$')
            await source_conn.run(f'echo "{escaped_key}" > {temp_key_path}')
            await source_conn.run(f'chmod 600 {temp_key_path}')

            # 2. Executa o rsync com a chave SSH temporária
            rsync_opts = f'-avz -e "ssh -i {temp_key_path} -o StrictHostKeyChecking=no"'
            rsync_cmd = f"rsync {rsync_opts} {source_tar_path} {username}@{target_ip}:{target_tar_path}"
            
            # Executamos como usuário comum (sem sudo) pois o rsync usa o túnel SSH do usuário dev
            logger.debug(f"Executando rsync: {rsync_cmd}")
            result = await source_conn.run(rsync_cmd)
            
            if result.exit_status != 0:
                stderr = result.stderr.strip() if result.stderr else "Sem saída de erro"
                raise RuntimeError(f"Falha na transferência via rsync [{result.exit_status}]: {stderr}")
            
            logger.info("Transferência via rsync concluída com sucesso.")

        finally:
            # 3. Garante a remoção segura da chave privada no nó de origem
            await source_conn.run(f"rm -f {temp_key_path}")

    async def transfer_path(
        self,
        source_conn,
        source_path: str,
        target_ip: str,
        target_path: str,
        private_key_content: str,
        username: str = "dev",
        is_dir: bool = False
    ) -> None:
        """
        Transfere um arquivo ou diretório do nó de origem diretamente para o destino via rsync.
        """
        temp_key_path = "/tmp/migration_transfer_key"
        logger.info(f"Transferindo {'diretorio' if is_dir else 'arquivo'} {source_path} para {target_ip}:{target_path}")

        try:
            # 1. Grava a chave privada temporariamente no nó de origem
            escaped_key = private_key_content.replace('"', '\\"').replace('$', '\\$')
            await source_conn.run(f'echo "{escaped_key}" > {temp_key_path}')
            await source_conn.run(f'chmod 600 {temp_key_path}')

            # 2. Executa o rsync com a chave SSH temporária
            rsync_opts = f'-avz -e "ssh -i {temp_key_path} -o StrictHostKeyChecking=no"'
            
            src = source_path
            dst = target_path
            if is_dir:
                if not src.endswith('/'):
                    src += '/'
                # Garante que o diretório de destino exista no outro host antes do rsync
                # O rsync com '/' no source copia o conteúdo da pasta para a pasta de destino.
                # Precisamos que a pasta de destino exista.
                # Usamos ssh para criar a pasta de destino.
                # Como rsync roda da origem ligando no destino via SSH,
                # podemos rodar mkdir -p via ssh usando a mesma chave, ou simplesmente deixar o rsync criar.
                # Na verdade, rsync -avz src/ dev@target:dst criará o diretório dst se ele não existir.
                # Mas para garantir, criamos o diretório de destino se ele não existir.
            
            rsync_cmd = f"rsync {rsync_opts} {src} {username}@{target_ip}:{dst}"
            logger.debug(f"Executando rsync: {rsync_cmd}")
            result = await source_conn.run(rsync_cmd)
            
            if result.exit_status != 0:
                stderr = result.stderr.strip() if result.stderr else "Sem saída de erro"
                raise RuntimeError(f"Falha na transferência via rsync [{result.exit_status}]: {stderr}")
            
            logger.info("Transferência via rsync concluída com sucesso.")

        finally:
            await source_conn.run(f"rm -f {temp_key_path}")

