# Local AI Research Stack

**What this repo provides**

- **Admission controller**: FastAPI UI + gRPC admission service implementing P1 token bucket, P2 FIFO with preemption, P3 opportunistic scheduler.
- **P2 worker**: gRPC worker with `Preempt` and `Resume` endpoints; atomic checkpoint persistence to `checkpoints.json`.
- **P3 worker**: FAISS `IndexIDMap` + SQLite metadata for real vector indexing and queries.
- **Test harness**: `loadgen.py` and `latency_probe.py` for noisy neighbor and latency validation.
- **Makefile**: reproducible build, run, and test commands.

---

## Prerequisites

- **OS**: Linux or macOS
- **Docker** and **docker-compose**
- **Python 3.9+** for local runs
- **pip** for installing Python dev dependencies
- Ports used:
  - **5001** FastAPI UI (Note: Port 5000 is used by macOS AirPlay)
  - **50051** gRPC admission
  - **50052** gRPC P2 worker
  - **8001** Prometheus metrics

---

## Quickstart using Docker Compose

1. **Build and start everything**
   ```bash
   make up
   ```
   *or to build images first:*
   ```bash
   make build
   make up
   ```

2. **Open the UI**
   Visit `http://localhost:5001` to view the admission controller dashboard.

3. **Metrics**
   Prometheus metrics are exposed at `http://localhost:8001/`.

4. **Stop**
   ```bash
   make down
   ```

## Run locally without Docker for development

1. **Generate gRPC code**
   ```bash
   make gen-protos
   ```

2. **Start services in separate terminals or background**
   ```bash
   # Terminal 1
   ./ml-env/bin/python p2_worker_stub.py

   # Terminal 2
   ./ml-env/bin/python p3_faiss_worker.py

   # Terminal 3
   ./ml-env/bin/python admission_controller_grpc.py
   ```
   Visit `http://localhost:5001` for the UI.

## Test and validate

### 1. P1 latency SLO
Run the latency probe for P1:
```bash
make test-latency
```
**Success criteria**: P50 < 200ms, P95 < 1s under light load.

### 2. Noisy neighbor resilience
Run a P3 noisy load and measure P1 latency concurrently:
```bash
# Start noisy P3 load
make test-noisy

# In another terminal run P1 probe
make test-latency
```
**Success criteria**: P1 latency remains within SLOs. No OOMs for Ling-like services if configured.

### 3. Preemption and checkpoint resume
Enqueue many P2 tasks:
```bash
./ml-env/bin/python loadgen.py --qps 20 --duration 60 --priority 2
```
Trigger P1 burst to force preemption:
```bash
./ml-env/bin/python loadgen.py --qps 50 --duration 30 --priority 1
```
Inspect checkpoint file:
```bash
ls -l checkpoints.json
cat checkpoints.json
```
Resume a checkpoint via the P2 worker gRPC `Resume` endpoint or by restarting the worker and calling the resume flow.

**Success criteria**: `checkpoints.json` contains checkpoint tokens and metadata. Resume returns `RESUMED` and task completes.

## Logs and troubleshooting
Tail logs for all services:
```bash
make logs
```

**Common issues**
- **gRPC import errors**: ensure `proto/*_pb2.py` and `proto/*_pb2_grpc.py` exist. Run `make gen-protos`.
- **Port conflicts**: ensure ports 5001, 50051, 50052, 8001 are free.
- **FAISS errors**: install faiss-cpu compatible with your Python version.
- **Checkpoint file missing**: ensure checkpoints are written in the working directory.

## Next steps and recommended improvements
- Add TLS and mTLS for gRPC channels.
- Persist checkpoints to a durable store for multi-host resilience.
- Add Grafana dashboard JSON and Prometheus alert rules for SLO violations.
- Replace local FAISS with a managed vector DB for scale.

## Useful Makefile commands
- `make gen-protos` generate gRPC code
- `make build` build docker images
- `make up` start stack with docker-compose
- `make down` stop stack
- `make logs` tail logs
- `make test-noisy` run P3 noisy load
- `make test-latency` run P1 latency probe
- `make run-local` run services locally without Docker
- `make demo` run the automated research snapshot demo
