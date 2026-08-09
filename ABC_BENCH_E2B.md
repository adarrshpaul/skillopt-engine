# ABC-Bench Dual-Container Architecture (E2B Integration)

To evaluate the SkillOpt Engine against the highly rigorous **ABC-Bench** dataset (which requires physical deployment of backend stacks, APIs, and databases), we have implemented a **Dual-Container Cloud-Hybrid Architecture**. 

Because running full Docker stacks locally alongside 16GB-bound LLMs causes catastrophic memory swapping and kernel panics on Apple Silicon (M-series), we have physically separated the Agent's reasoning layer from its deployment execution layer.

## The Dual-Container Concept

1. **Agent Container (Local MacBook M5, 16GB)**
   - Runs the `terminal-bench` CLI.
   - Runs our custom `custom_nanobot_adapter.py`.
   - Runs the Nanobot ReAct loop, evaluating tasks with `Ling-3.0` (Planner) and `Ornith-9B` (Coder).
   - *Result*: Zero RAM wasted on running bloated Java/Node backend containers. 100% of Unified Memory is dedicated to model inference.

2. **Target Container (E2B Cloud Sandbox)**
   - When the agent decides to execute a build script, deploy an API, or run tests (e.g., `npm run test`, `docker-compose up`), the command is intercepted by `nanobot/agent/tools/e2b_tool.py`.
   - The command is securely executed in an isolated [E2B Sandbox](https://e2b.dev/) in the cloud.
   - Outputs (`stdout`, `stderr`) are piped directly back to the local agent as if it ran on the local machine.

## Setup Instructions

### 1. Requirements
- Python 3.12+ (Specifically required by `terminal-bench`)
- An active E2B API Key.

### 2. Installation
We recommend using `uv` to manage the isolated environment for the benchmark runner to avoid polluting the core SkillOpt `venv`.

```bash
# Create the environment
uv venv --python 3.12 tb-env
source tb-env/bin/activate

# Install the benchmark CLI and E2B SDK
uv pip install terminal-bench e2b datasets huggingface_hub
```

### 3. Download the Dataset
The ABC-Bench dataset contains tasks that require complex verification. 

```bash
# We use the python script approach to download the dataset locally
python3 -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='OpenMOSS-Team/ABC-Bench', repo_type='dataset', local_dir='ABC-Bench-Dataset')"
```

## Running the Benchmark

Because we are utilizing cloud compute (E2B) and constrained local hardware, it is **critical** to enforce strict timeouts and concurrency limits to prevent credit-drain and thermal throttling.

Run the evaluation using the custom Nanobot adapter:

```bash
export E2B_API_KEY="your_e2b_api_key_here"

# Execute the benchmark
tb run \
  --dataset-path ./ABC-Bench-Dataset \
  --agent custom_nanobot_adapter.py \
  --n-attempts 1 \
  --global-agent-timeout-sec 600 \
  --n-concurrent 1
```

### Parameter Breakdown
- `--agent custom_nanobot_adapter.py`: Instructs `terminal-bench` to bypass its native agents (like OpenHands) and bridge into our local Nanobot ReAct loop.
- `--n-attempts 1`: Prevents infinite retry loops if the target environment catastrophically fails to build.
- `--global-agent-timeout-sec 600`: Hard 10-minute kill switch to save E2B credits.
- `--n-concurrent 1`: Forces sequential task evaluation. Never run >1 locally on a 16GB Mac.

## Extending the Adapter
If you wish to modify how Nanobot initializes or add more advanced tools (like semantic search over the target repository), edit `custom_nanobot_adapter.py`. The script implements `terminal_bench.agents.base_agent.BaseAgent` and handles the handover between the harness and the E2B-enabled Nanobot loop.
