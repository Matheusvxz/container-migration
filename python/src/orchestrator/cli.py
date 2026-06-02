#!/usr/bin/env python3
import argparse
import sys
import os
import time

import grpc

try:
    from orchestrator.proto import migration_pb2
    from orchestrator.proto import migration_pb2_grpc
except ImportError:
    print("ERRO: Os stubs gRPC não foram encontrados. Por favor, execute compile_proto.py primeiro.", file=sys.stderr)
    sys.exit(1)


def get_stub(server_address: str):
    """Cria o canal gRPC e retorna o stub de comunicação."""
    channel = grpc.insecure_channel(server_address)
    stub = migration_pb2_grpc.MigrationServiceStub(channel)
    return channel, stub


def cmd_list(args):
    """Lista o estado atual do cluster e contêineres a partir do daemon."""
    channel, stub = get_stub(args.server)
    try:
        response = stub.ListNodes(migration_pb2.Empty())
        print("\n" + "="*80)
        print(f"{'ESTADO DO CLUSTER (VIA DAEMON gRPC)':^80}")
        print("="*80)
        
        for node in response.nodes:
            print(f"\n[Host] IP: {node.ip} | Status: {node.status}")
            if node.error_msg:
                print(f"  └─ Erro: {node.error_msg}")
            
            if node.containers:
                print("  └─ Contêineres ativos:")
                for c in node.containers:
                    print(f"     ├── ID: {c.id[:12]} | Nome: {c.name:<15} | Estado: {c.state:<15} | Imagem: {c.image}")
            else:
                print("  └─ Nenhum contêiner ativo.")
        print("="*80 + "\n")
    except Exception as e:
        print(f"Erro ao conectar ao Daemon gRPC ({args.server}): {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        channel.close()


def cmd_migrate(args):
    """Envia uma solicitação de migração para o daemon."""
    channel, stub = get_stub(args.server)
    try:
        print(f"Enviando pedido de migração para o Daemon...")
        request = migration_pb2.MigrateRequest(
            container_id=args.container,
            source_ip=args.source,
            target_ip=args.target,
            pre_dumps_count=args.pre_dumps
        )
        
        response = stub.MigrateContainer(request)
        job_id = response.job_id
        print(f"SUCESSO: Job de migração iniciado no Daemon! ID: {job_id}")
        
        if args.watch:
            print("\nMonitorando progresso em tempo real (Ctrl+C para sair do monitoramento)...")
            while True:
                job_status = stub.GetJobStatus(migration_pb2.JobStatusRequest(job_id=job_id))
                print(f"  [{time.strftime('%H:%M:%S')}] Status: {job_status.status:<12} | Passo: {job_status.step:<25}")
                
                if job_status.status == "COMPLETED":
                    print("\n🎉 MIGRADO COM SUCESSO!")
                    break
                elif job_status.status == "FAILED":
                    print(f"\n❌ ERRO NA MIGRAÇÃO: {job_status.error_msg}")
                    break
                
                time.sleep(2)
    except Exception as e:
        print(f"Erro ao processar migração: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        channel.close()


def cmd_run(args):
    """Envia uma solicitação para inicializar pod/container em um nó específico."""
    channel, stub = get_stub(args.server)
    try:
        print(f"Enviando pedido para inicializar contêiner no nó {args.node}...")
        request = migration_pb2.StartContainerRequest(
            node_ip=args.node,
            pod_config_path=args.pod_config,
            container_config_path=args.container_config
        )
        
        response = stub.StartContainer(request)
        print(f"SUCESSO: {response.message}")
        print(f"  ID do Pod: {response.pod_id}")
        print(f"  ID do Contêiner: {response.container_id}")
    except Exception as e:
        print(f"Erro ao inicializar contêiner: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        channel.close()


def cmd_jobs(args):
    """Lista todos os jobs de migração registrados no daemon."""
    channel, stub = get_stub(args.server)
    try:
        response = stub.ListJobs(migration_pb2.Empty())
        if not response.jobs:
            print("Nenhum job de migração ativo ou concluído.")
            return

        print("\n" + "-"*80)
        print(f"{'MIGRAÇÕES REGISTRADAS NO DAEMON':^80}")
        print("-"*80)
        for job in response.jobs:
            print(f"Job: {job.job_id[:8]} | Container: {job.container_id[:12]} | De: {job.source_ip} -> Para: {job.target_ip}")
            print(f"  Status: {job.status:<12} | Passo atual: {job.step:<25}")
            if job.error_msg:
                print(f"  Erro: {job.error_msg}")
            if job.end_time > 0:
                duration = job.end_time - job.start_time
                print(f"  Duração: {duration:.2f}s")
            print("-"*80)
    except Exception as e:
        print(f"Erro ao listar jobs: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        channel.close()


def cmd_status(args):
    """Exibe o status atual de um job de migração específico."""
    channel, stub = get_stub(args.server)
    try:
        job_status = stub.GetJobStatus(migration_pb2.JobStatusRequest(job_id=args.job))
        print(f"Job ID: {job_status.job_id}")
        print(f"Container: {job_status.container_id[:12]}")
        print(f"De: {job_status.source_ip} -> Para: {job_status.target_ip}")
        print(f"Status: {job_status.status}")
        print(f"Passo Atual: {job_status.step}")
        if job_status.error_msg:
            print(f"Erro: {job_status.error_msg}")
        if job_status.end_time > 0:
            print(f"Duração: {job_status.end_time - job_status.start_time:.2f}s")
    except Exception as e:
        print(f"Erro ao obter status do job: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        channel.close()


def cmd_refresh(args):
    """Força o rescan de contêineres nos hosts do daemon."""
    channel, stub = get_stub(args.server)
    try:
        print("Solicitando varredura imediata dos hosts ao Daemon...")
        stub.Refresh(migration_pb2.Empty())
        print("Varredura concluída com sucesso no Daemon!")
    except Exception as e:
        print(f"Erro ao forçar atualização: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        channel.close()


def cmd_add(args):
    """Adiciona um nó ao daemon."""
    channel, stub = get_stub(args.server)
    try:
        print(f"Solicitando adição do nó {args.ip} ao Daemon...")
        request = migration_pb2.AddNodeRequest(ip=args.ip)
        response = stub.AddNode(request)
        if response.success:
            print(f"SUCESSO: {response.message}")
        else:
            print(f"FALHA: {response.message}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Erro ao adicionar nó: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        channel.close()


def cmd_remove(args):
    """Remove um nó do daemon."""
    channel, stub = get_stub(args.server)
    try:
        print(f"Solicitando remoção do nó {args.ip} ao Daemon...")
        request = migration_pb2.RemoveNodeRequest(ip=args.ip)
        response = stub.RemoveNode(request)
        if response.success:
            print(f"SUCESSO: {response.message}")
        else:
            print(f"FALHA: {response.message}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Erro ao remover nó: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        channel.close()


def cmd_set(args):
    """Define a lista de nós do daemon."""
    channel, stub = get_stub(args.server)
    try:
        print(f"Solicitando definição de nós para: {', '.join(args.ips)}...")
        request = migration_pb2.SetNodesRequest(ips=args.ips)
        response = stub.SetNodes(request)
        if response.success:
            print(f"SUCESSO: {response.message}")
        else:
            print(f"FALHA: {response.message}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Erro ao definir nós: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        channel.close()


def cmd_interactive_start(args):
    """Envia uma solicitação para iniciar a migração interativa (síncrona)."""
    channel, stub = get_stub(args.server)
    try:
        print(f"Iniciando sessão de migração interativa para o container {args.container[:12]}...")
        request = migration_pb2.StartInteractiveMigrateRequest(
            container_id=args.container,
            source_ip=args.source,
            target_ip=args.target,
            pod_config_path=args.pod_config or "",
            container_config_path=args.container_config or ""
        )
        response = stub.StartInteractiveMigrate(request)
        print(f"SUCESSO: {response.message}")
        print(f"  ID do Job de Migração: {response.job_id}")
        print(f"Guarde este ID para executar os próximos passos ('pre-dump' e 'final').")
    except Exception as e:
        print(f"Erro ao iniciar migração interativa: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        channel.close()


def cmd_interactive_pre_dump(args):
    """Executa um pre-dump incremental e opcionalmente o transfere (síncrono)."""
    channel, stub = get_stub(args.server)
    try:
        if args.transfer:
            print(f"Gerando pre-dump incremental para o Job {args.job[:8]} e transferindo para o destino...")
        else:
            print(f"Gerando pre-dump incremental localmente na origem para o Job {args.job[:8]}...")
            
        request = migration_pb2.PreDumpInteractiveRequest(
            job_id=args.job,
            transfer=args.transfer
        )
        response = stub.PreDumpInteractive(request)
        print(f"SUCESSO: {response.message}")
        print(f"  Iteração: {response.iteration}")
        print(f"  Transferido: {'Sim' if response.transferred else 'Não'}")
    except Exception as e:
        print(f"Erro ao executar pre-dump interativo: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        channel.close()


def cmd_interactive_final(args):
    """Executa a fase final: para container, faz dump final, transfere, consolida e restaura. Monitora em tempo real."""
    channel, stub = get_stub(args.server)
    try:
        print(f"Solicitando finalização da migração interativa para o Job {args.job[:8]}...")
        request = migration_pb2.FinalInteractiveMigrateRequest(
            job_id=args.job
        )
        response = stub.FinalInteractiveMigrate(request)
        job_id = response.job_id
        print(f"SUCESSO: Fluxo final de migração iniciado no Daemon! ID: {job_id}")
        
        print("\nMonitorando finalização em tempo real (Ctrl+C para sair do monitoramento)...")
        last_step = ""
        while True:
            job_status = stub.GetJobStatus(migration_pb2.JobStatusRequest(job_id=job_id))
            
            current_step_status = f"Status: {job_status.status:<12} | Passo: {job_status.step:<25}"
            if current_step_status != last_step:
                print(f"  [{time.strftime('%H:%M:%S')}] {current_step_status}")
                last_step = current_step_status
            
            if job_status.status == "COMPLETED":
                print("\n🎉 RESTAURADO E MIGRADO COM SUCESSO NO DESTINO!")
                break
            elif job_status.status == "FAILED":
                print(f"\n❌ ERRO NA FINALIZAÇÃO DA MIGRAÇÃO: {job_status.error_msg}")
                sys.exit(1)
                
            time.sleep(1)
    except Exception as e:
        print(f"Erro ao finalizar migração interativa: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        channel.close()


def cmd_migrate_interactive(args):
    """Direciona para as ações start, pre-dump ou final da migração interativa."""
    if args.action == "start":
        cmd_interactive_start(args)
    elif args.action == "pre-dump":
        cmd_interactive_pre_dump(args)
    elif args.action == "final":
        cmd_interactive_final(args)


def main():
    parser = argparse.ArgumentParser(
        description="CLI para interagir com o Orquestrador de Migração de Contêineres (via Daemon gRPC)"
    )
    parser.add_argument(
        "-s", "--server",
        default="localhost:50051",
        help="Endereço do servidor Daemon gRPC (padrão: localhost:50051)"
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcomandos de execução")
    
    # Subcomando list
    subparsers.add_parser("list", help="Lista nós, contêineres e seus respectivos estados reais")
    
    # Subcomando migrate
    migrate_parser = subparsers.add_parser("migrate", help="Dispara a migração assíncrona de um contêiner")
    migrate_parser.add_argument("--container", required=True, help="ID do contêiner a ser migrado")
    migrate_parser.add_argument("--source", required=True, help="IP do nó de origem")
    migrate_parser.add_argument("--target", required=True, help="IP do nó de destino")
    migrate_parser.add_argument("--pre-dumps", type=int, default=2, help="Número de pre-dumps incrementais (padrão: 2)")
    migrate_parser.add_argument("--watch", action="store_true", help="Acompanha a migração em tempo real até o fim")

    # Subcomando migrate-interactive
    interactive_parser = subparsers.add_parser("migrate-interactive", help="Orquestração interativa de migração passo-a-passo")
    interactive_subparsers = interactive_parser.add_subparsers(dest="action", required=True, help="Ações de migração interativa")
    
    start_parser = interactive_subparsers.add_parser("start", help="Inicializa a sessão de migração interativa")
    start_parser.add_argument("--container", required=True, help="ID do contêiner a ser migrado")
    start_parser.add_argument("--source", required=True, help="IP do nó de origem")
    start_parser.add_argument("--target", required=True, help="IP do nó de destino")
    start_parser.add_argument("--pod-config", help="Caminho opcional do arquivo local JSON do Pod (na controladora)")
    start_parser.add_argument("--container-config", help="Caminho opcional do arquivo local JSON do Contêiner (na controladora)")
    
    predump_parser = interactive_subparsers.add_parser("pre-dump", help="Gera um pre-dump incremental e opcionalmente o envia")
    predump_parser.add_argument("--job", required=True, help="UUID da sessão de migração interativa")
    predump_parser.add_argument("--transfer", action="store_true", help="Envia o pre-dump gerado imediatamente para o nó de destino")
    
    final_parser = interactive_subparsers.add_parser("final", help="Finaliza a migração interativa, para o contêiner e o restaura no destino")
    final_parser.add_argument("--job", required=True, help="UUID da sessão de migração interativa")
    
    # Subcomando jobs
    subparsers.add_parser("jobs", help="Lista todos os jobs de migração registrados no daemon")
    
    # Subcomando status
    status_parser = subparsers.add_parser("status", help="Consulta o status e passo atual de uma migração específica")
    status_parser.add_argument("--job", required=True, help="UUID do Job de migração")
    
    # Subcomando refresh
    subparsers.add_parser("refresh", help="Força uma nova varredura de contêineres nos hosts do daemon")
    
    # Subcomando run
    run_parser = subparsers.add_parser("run", help="Inicializa um pod e contêiner em um nó a partir de arquivos locais de configuração")
    run_parser.add_argument("--node", required=True, help="IP do nó de computação onde o contêiner deve ser iniciado")
    run_parser.add_argument("--pod-config", required=True, help="Caminho do arquivo local JSON do Pod (na controladora)")
    run_parser.add_argument("--container-config", required=True, help="Caminho do arquivo local JSON do Contêiner (na controladora)")

    # Subcomando add
    add_parser = subparsers.add_parser("add", help="Adiciona um novo nó/host ao orquestrador")
    add_parser.add_argument("ip", help="IP do nó a ser adicionado")
    
    # Subcomando remove
    remove_parser = subparsers.add_parser("remove", help="Remove um nó/host do orquestrador")
    remove_parser.add_argument("ip", help="IP do nó a ser removido")
    
    # Subcomando set
    set_parser = subparsers.add_parser("set", help="Define a lista completa de nós/hosts do orquestrador")
    set_parser.add_argument("ips", nargs="+", help="Lista de IPs dos nós (separados por espaço)")

    args = parser.parse_args()

    # Mapeamento de subcomandos
    if args.command == "list":
        cmd_list(args)
    elif args.command == "migrate":
        cmd_migrate(args)
    elif args.command == "jobs":
        cmd_jobs(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "refresh":
        cmd_refresh(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "remove":
        cmd_remove(args)
    elif args.command == "set":
        cmd_set(args)
    elif args.command == "migrate-interactive":
        cmd_migrate_interactive(args)

if __name__ == "__main__":
    main()
