#!/usr/bin/env python3
import os
import sys
import subprocess

def compile_proto():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    proto_dir = os.path.join(project_root, "proto")
    proto_path = os.path.join(proto_dir, "migration.proto")
    out_dir = os.path.join(project_root, "src", "orchestrator", "proto")
    
    if not os.path.exists(proto_path):
        print(f"Erro: Arquivo proto não encontrado em {proto_path}", file=sys.stderr)
        sys.exit(1)
        
    os.makedirs(out_dir, exist_ok=True)
    print(f"Compilando {proto_path} para {out_dir}...")
    
    # Executa a compilação utilizando grpc_tools.protoc integrado no Python
    try:
        import grpc_tools.protoc
        args = [
            "grpc_tools.protoc",
            f"-I{proto_dir}",
            f"--python_out={out_dir}",
            f"--grpc_python_out={out_dir}",
            proto_path
        ]
        
        result = grpc_tools.protoc.main(args)
        if result != 0:
            print("Erro na compilação do gRPC", file=sys.stderr)
            sys.exit(result)
            
        print("Stubs gRPC compilados com sucesso!")
        
    except ImportError:
        # Tenta via linha de comando caso o módulo não esteja importável no Python atual
        cmd = [
            sys.executable, "-m", "grpc_tools.protoc",
            f"-I{proto_dir}",
            f"--python_out={out_dir}",
            f"--grpc_python_out={out_dir}",
            proto_path
        ]
        try:
            subprocess.run(cmd, check=True)
            print("Stubs gRPC compilados via subprocesso com sucesso!")
        except Exception as e:
            print(f"Erro ao tentar compilar stubs: {e}", file=sys.stderr)
            print("Certifique-se de que o pacote 'grpcio-tools' está instalado no ambiente.", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    compile_proto()
