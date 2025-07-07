#!/bin/bash
# Generate Python gRPC code from .proto file into src/ for 'from src import mixnet_pb2' imports
python -m grpc_tools.protoc -I=protos --python_out=src --grpc_python_out=src protos/mixnet.proto
