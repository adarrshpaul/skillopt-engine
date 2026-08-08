# Makefile for local AI research stack
.PHONY: all gen-protos build images up down logs clean test-noisy test-latency run-local demo

PYTHON=./ml-env/bin/python
GRPC_TOOLS=$(PYTHON) -m grpc_tools.protoc
PROTO_DIR=proto
PROTO_FILES=$(PROTO_DIR)/admission.proto $(PROTO_DIR)/worker.proto

# Docker images
IMAGE_ADMISSION=local/admission:latest
IMAGE_P2=local/p2worker:latest
IMAGE_P3=local/p3worker:latest

all: build

# Generate Python gRPC code from proto files
gen-protos:
	@echo "Generating gRPC Python code..."
	$(GRPC_TOOLS) -I=$(PROTO_DIR) --python_out=proto --grpc_python_out=proto $(PROTO_FILES)
	@echo "Protos generated in proto/"

# Build local docker images (Assumes Dockerfiles exist)
build: gen-protos images

images:
	@echo "Building docker images..."
	docker build -f Dockerfile.admission -t $(IMAGE_ADMISSION) .
	docker build -f Dockerfile.p2worker -t $(IMAGE_P2) .
	docker build -f Dockerfile.p3worker -t $(IMAGE_P3) .
	@echo "Images built: $(IMAGE_ADMISSION), $(IMAGE_P2), $(IMAGE_P3)"

# Start stack with docker-compose
up:
	docker-compose up --build -d

# Stop stack
down:
	docker-compose down

# Tail logs for all services
logs:
	docker-compose logs -f --tail=200

# Remove built images and temporary artifacts
clean:
	@echo "Stopping containers and removing images..."
	docker-compose down --rmi local -v --remove-orphans || true
	-rm -f proto/*_pb2.py proto/*_pb2_grpc.py
	@kill `cat admission.pid p2_worker.pid` 2>/dev/null || true
	rm -f admission.pid p2_worker.pid
	rm -f checkpoints.json checkpoints.json.tmp p3_metadata.db faiss_index.bin manifest.json snapshot.tar.gz
	@echo "Clean complete."

# Run tests using the provided test harness scripts
test-noisy:
	@echo "Starting noisy neighbor test: P3 high QPS"
	$(PYTHON) loadgen.py --qps 50 --duration 120 --priority 3

test-latency:
	@echo "Running P1 latency probe"
	$(PYTHON) latency_probe.py --qps 5 --duration 120

# Run services locally without Docker for development
run-local:
	@echo "Starting P2 worker and Master Cockpit (:5002) locally..."
	$(PYTHON) p2_worker_stub.py & \
	$(PYTHON) master_cockpit.py

# Automated demo run
demo:
	@echo "Starting FastAPI Admission Controller & P2 Worker Stub in background..."
	$(PYTHON) admission_controller_grpc.py & echo $$! > admission.pid
	$(PYTHON) p2_worker_stub.py & echo $$! > p2_worker.pid
	@echo "Running P3 worker mock to initialize index..."
	$(PYTHON) p3_faiss_worker.py
	@echo "Waiting 5 seconds for servers to start..."
	@sleep 5
	@echo "Running a mock P1 request to FastAPI Admission controller..."
	curl -s -X POST -H "Content-Type: application/json" -d '{"priority": 1, "id": "req-p1-1"}' http://localhost:5001/admit
	@echo "\nRunning a mock P2 request to trigger queueing..."
	curl -s -X POST -H "Content-Type: application/json" -d '{"priority": 2, "id": "req-p2-1"}' http://localhost:5001/admit
	@echo "\nWaiting a moment to let P2 worker process..."
	@sleep 2
	@echo "Creating manifest.json..."
	@echo '{"model_hashes": {"ling": "abc1234", "ornith": "def5678"}, "quantization": "Q5_K_M", "index_type": "IndexFlatL2"}' > manifest.json
	@echo "Demo complete! Snapshotting FAISS and SQLite..."
	@tar -czf snapshot.tar.gz p3_metadata.db faiss_index.bin manifest.json checkpoints.json
	@echo "Cleaning up background processes..."
	@kill `cat admission.pid p2_worker.pid` 2>/dev/null || true
	@rm -f admission.pid p2_worker.pid
	@echo "Done!"

# Convenience target to generate protos and run compose up
deploy: gen-protos up
	@echo "Deployment complete. UI: http://localhost:5001 Metrics: http://localhost:8001 gRPC: localhost:50051"

# Test targets
test-unit:
	@echo "Running unit tests..."
	$(PYTHON) -m pytest tests/test_model_router.py tests/test_graph_store.py \
		tests/test_admission_unit.py tests/test_checkpoint.py \
		tests/test_faiss_worker.py tests/test_graph_api.py -v --tb=short

test-integration:
	@echo "Running integration tests (services must be running)..."
	$(PYTHON) -m pytest tests/test_integration_admission_worker.py \
		tests/test_integration_graph_chain.py \
		tests/test_integration_model_routing.py \
		tests/test_integration_faiss_graph.py -v --tb=short

test-all: test-unit test-integration
