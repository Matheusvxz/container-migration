#!/usr/bin/env node
import { execSync } from 'node:child_process';
import { program } from 'commander';
import * as p from '@clack/prompts';
import color from 'picocolors';

interface GCPImage {
  name: string;
  family?: string;
  status: string;
  creationTimestamp: string;
  diskSizeGb?: string;
}

// Custom exec sync helper that runs a command and returns output, or throws
function runCommand(cmd: string): string {
  try {
    return execSync(cmd, { stdio: ['pipe', 'pipe', 'pipe'], encoding: 'utf-8' }).trim();
  } catch (err: any) {
    const stderr = err.stderr ? err.stderr.toString().trim() : '';
    throw new Error(stderr || err.message || 'Unknown error');
  }
}

async function main() {
  // Setup commander for parsing CLI arguments
  program
    .name('gcp-images')
    .description('CLI interativa para listar e deletar imagens customizadas da GCP')
    .option('-p, --project <id>', 'ID do projeto da GCP')
    .option('-d, --dry-run', 'Apenas simula as deleções sem executá-las no GCP')
    .parse(process.argv);

  const options = program.opts();

  p.intro(color.bgCyan(color.black(' GCP Custom Images Manager ')));

  // 1. Determine or prompt for project ID
  let projectId = options.project;
  const s = p.spinner();

  if (!projectId) {
    s.start('Detectando projeto GCP ativo...');
    try {
      projectId = runCommand('gcloud config get-value project');
      if (!projectId || projectId === '(unset)') {
        s.stop('Nenhum projeto ativo configurado no gcloud');
        const inputProject = await p.text({
          message: 'Por favor, insira o ID do projeto GCP:',
          placeholder: 'meu-projeto-gcp-123',
          validate(value) {
            if (value.trim().length === 0) return 'O ID do projeto é obrigatório';
          },
        });
        if (p.isCancel(inputProject)) {
          p.cancel('Operação cancelada.');
          process.exit(0);
        }
        projectId = inputProject.trim();
      } else {
        s.stop(`Projeto GCP ativo detectado: ${color.cyan(projectId)}`);
      }
    } catch (err: any) {
      s.stop(`Erro ao tentar ler o projeto ativo do gcloud: ${err.message}`);
      const inputProject = await p.text({
        message: 'Por favor, insira o ID do projeto GCP:',
        placeholder: 'meu-projeto-gcp-123',
        validate(value) {
          if (value.trim().length === 0) return 'O ID do projeto é obrigatório';
        },
      });
      if (p.isCancel(inputProject)) {
        p.cancel('Operação cancelada.');
        process.exit(0);
      }
      projectId = inputProject.trim();
    }
  } else {
    p.note(`Usando o projeto GCP especificado via argumento: ${color.cyan(projectId)}`);
  }

  // 2. Fetch custom images
  s.start(`Buscando imagens customizadas no projeto ${color.cyan(projectId)}...`);
  let images: GCPImage[] = [];
  try {
    const listCmd = `gcloud compute images list --no-standard-images --format="json" --project="${projectId}"`;
    const output = runCommand(listCmd);
    images = JSON.parse(output) as GCPImage[];
    s.stop(`Busca concluída. ${color.green(images.length)} imagem(ns) encontrada(s).`);
  } catch (err: any) {
    s.stop(color.red('Erro ao buscar imagens no GCP!'));
    p.log.error(color.red(err.message));
    p.note('Certifique-se de que o gcloud está instalado, autenticado (gcloud auth login) e que você tem permissão no projeto.');
    p.cancel('Operação abortada.');
    process.exit(1);
  }

  if (images.length === 0) {
    p.outro(color.yellow('Nenhuma imagem customizada encontrada neste projeto GCP.'));
    process.exit(0);
  }

  // Sort images: newest first
  images.sort((a, b) => new Date(b.creationTimestamp).getTime() - new Date(a.creationTimestamp).getTime());

  // 3. User Selects images to delete
  const selectOptions = images.map((img) => {
    const createdDate = new Date(img.creationTimestamp).toLocaleDateString('pt-BR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
    const sizeStr = img.diskSizeGb ? ` (${img.diskSizeGb} GB)` : '';
    const familyStr = img.family ? ` | Família: ${img.family}` : '';
    return {
      value: img.name,
      label: img.name,
      hint: `Criada em: ${createdDate}${sizeStr}${familyStr} | Status: ${img.status}`,
    };
  });

  const selectedImages = await p.multiselect({
    message: 'Selecione as imagens que deseja deletar (use Espaço para marcar, Enter para confirmar):',
    options: selectOptions,
    required: false,
  });

  if (p.isCancel(selectedImages)) {
    p.cancel('Operação cancelada pelo usuário.');
    process.exit(0);
  }

  if (!selectedImages || selectedImages.length === 0) {
    p.outro(color.yellow('Nenhuma imagem foi selecionada para exclusão. Encerrando.'));
    process.exit(0);
  }

  // 4. Confirm Deletion
  const confirmMessage = options.dryRun
    ? `[DRY-RUN] Deseja simular a exclusão de ${color.red(selectedImages.length)} imagem(ns) selecionada(s)?`
    : `Deseja realmente deletar ${color.red(selectedImages.length)} imagem(ns) selecionada(s) do GCP?`;

  const confirmed = await p.confirm({
    message: confirmMessage,
    active: 'Sim, prosseguir',
    inactive: 'Não, cancelar',
  });

  if (p.isCancel(confirmed) || !confirmed) {
    p.cancel('Deleção cancelada.');
    process.exit(0);
  }

  // 5. Execute Deletions
  const total = selectedImages.length;
  let successCount = 0;
  let failCount = 0;

  p.log.info(color.yellow(`Iniciando a remoção de ${total} imagem(ns)...`));

  for (let i = 0; i < total; i++) {
    const imageName = selectedImages[i] as string;
    const progress = `[${i + 1}/${total}]`;
    
    if (options.dryRun) {
      p.log.warn(`${progress} [DRY-RUN] Simulação de remoção para: ${color.cyan(imageName)}`);
      successCount++;
      continue;
    }

    s.start(`${progress} Deletando ${color.cyan(imageName)}...`);
    try {
      const deleteCmd = `gcloud compute images delete "${imageName}" --project="${projectId}" --quiet`;
      runCommand(deleteCmd);
      s.stop(`${progress} ${color.green('Sucesso!')} Imagem deletada: ${color.cyan(imageName)}`);
      successCount++;
    } catch (err: any) {
      s.stop(`${progress} ${color.red('Erro!')} Falha ao deletar: ${color.cyan(imageName)}`);
      p.log.error(color.red(err.message));
      failCount++;
    }
  }

  // 6. Conclusion
  const summaryMsg = options.dryRun
    ? `Simulação concluída. ${color.green(successCount)} imagens seriam deletadas.`
    : `Processamento finalizado. Sucesso: ${color.green(successCount)} | Falha(s): ${color.red(failCount)}`;

  p.outro(color.bgCyan(color.black(` ${summaryMsg} `)));
}

main().catch((err) => {
  p.log.error(color.red(`Ocorreu um erro fatal: ${err.message}`));
  process.exit(1);
});
