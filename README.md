# SkillOpt Engine

The SkillOpt Engine is a disciplined, Claude Code Harness-inspired governance framework for multi-agent coding workflows. It provides strict routing, safety guarantees, and evidentiary test pipelines for running local AI models on Apple Silicon.

## Core Architecture

### 1. The Orchestrator (`orchestrator.py`)
- **Multi-Agent Routing**: Uses `Ling-3.0` (Port `:8801`) as the "Planner" and "Reviewer" subagents, while `Ornith-9B` (Port `:8800`) executes "Coder" tasks.
- **Severity-Tiered Review Loop**: Implements a strict Maker-Checker loop with granular severity tiers (`CRITICAL`, `MAJOR`, `MINOR`, `RECOMMENDATION`). Fixes loop up to 3 times before escalating.
- **Runtime Safety Floor**: Hard boundaries prevent destructive commands (`rm -rf`, `mkfs`) or unbounded network egress (`curl`, `wget`) from being executed by generated code. Workspaces are fully bounded.
- **Evidentiary Output**: Automatically generates a `completion_report.md` ledger at the end of execution to provide proof of validation.

### 2. Fleet & Model Management
- **Master Cockpit**: A centralized UI and API at `:5002` that tracks real-time model telemetry, token consumption, and P1/P2/P3 queue health.
- **Centralized Router (`model_router.py`)**: Single source of truth for mapping AI roles (planner, reviewer, coder, fallback) to active endpoints.

### 3. Admission Controller
A gRPC-based priority queue handling requests across the fleet:
- **P1 (Interactive)**: High-priority token bucket for user interactions.
- **P2 (Planner Tasks)**: FIFO queue for complex task execution, with preemption capabilities.
- **P3 (Background)**: Opportunistic scheduling for tasks like FAISS vector indexing, dynamically throttled based on CPU utilization.

---

## Getting Started

### Prerequisites
- macOS (Apple Silicon optimized) or Linux
- Python 3.11+
- `uv` or `pip` for dependency management

### Installation & System Validation
Run the system validation script to ensure all components and models are properly wired:
```bash
./tests/validate-system.sh
```
This script runs a 36-point pre-flight check across services, schema boundaries, test fixtures, and ports.

### Running Tests
The testing framework uses JSON fixtures to strictly validate the admission controller and API schemas. 
```bash
# Install dependencies
pip install pytest faiss-cpu sentence-transformers

# Run the full test suite
python -m pytest tests/ -v
```

---

## Directory Structure
- `orchestrator.py` - Main entry point for the Multi-Agent Loop
- `master_cockpit.py` - UI and Telemetry engine
- `model_router.py` - Single source of truth for AI role mappings
- `admission_controller_grpc.py` - Core traffic shaping logic
- `tests/` - Comprehensive fixture-based and API schema tests
- `proto/` - gRPC definitions for the fleet

## License
MIT License
