import sys
import os

# Adiciona o diretório atual ao sys.path durante a importação dos stubs gRPC
# Isso resolve a importação interna do gRPC entre migration_pb2_grpc -> migration_pb2
sys.path.insert(0, os.path.dirname(__file__))
