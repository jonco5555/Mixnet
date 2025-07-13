#!/bin/bash
# Generate Python gRPC code from .proto file into src/mixnet/ for 'from src import mixnet_pb2' imports
python -m grpc_tools.protoc -I=protos --python_out=src/mixnet/ --grpc_python_out=src/mixnet/ protos/mixnet.proto
