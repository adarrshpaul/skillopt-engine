# ABC-Bench: Free-Tier Cloud Sandboxes

Running advanced benchmarks like ABC-Bench requires spinning up complex backend environments (e.g. Java Spring Boot + MySQL). Attempting this on a 16GB macOS machine will cause catastrophic disk swapping and freeze the system because Docker Desktop spins up a 2-4GB Linux VM just to exist.

To solve this, we use the `DOCKER_HOST` architecture to completely offload container execution from your local Mac to a remote free-tier cloud sandbox.

## Option 1: GitHub Codespaces Setup (Recommended)
Because GitHub owns both the cloud environment and the CLI, connecting your local agent to a Codespace requires almost zero configuration.

### The Free Tier
GitHub Free gives personal accounts 120 core-hours per month. If you spin up a standard 2-core / 4GB RAM Codespace, that equals 60 free hours of execution time every month.

### Step 1: Install and Authenticate the GitHub CLI
On your M5 Mac, open your terminal and install the `gh` CLI:
```bash
brew install gh
gh auth login
```
*(Follow the prompts to log in via your browser. Select "SSH" as your preferred protocol when asked).*

### Step 2: Spin Up a Codespace
Create a new Codespace tied to your ABC-Bench repository (or any dummy repo):
```bash
gh codespace create -r your-username/abc-bench-tasks
```
The CLI will return a unique Codespace name (e.g., `friendly-octo-robot`).

### Step 3: The Magic Agent Command
You don't need to manually configure SSH keys. The `gh` CLI has a built-in SSH wrapper that your agent can use to fire commands directly into the cloud. You can test it in your terminal right now:
```bash
gh codespace ssh -c friendly-octo-robot -- "docker ps"
```
Notice the `--` syntax. Anything after the `--` gets executed securely inside the remote Linux container.

### Step 4: Exporting DOCKER_HOST
To make the `terminal-bench` framework (and its Python `docker` library) recognize this Codespace as the native Docker daemon, we generate the SSH config for the Codespace and export it:
```bash
# Append the dynamic Codespace SSH configuration to your local SSH config
gh codespace ssh -c friendly-octo-robot --config >> ~/.ssh/config

# Now you can seamlessly set DOCKER_HOST to point to it
export DOCKER_HOST="ssh://codespace.friendly-octo-robot"
```
Once `DOCKER_HOST` is exported, simply run `./scripts/run_benchmark_remote.sh` and the benchmark will execute in the cloud!

---

## Option 2: Gitpod (The 50-Hour Alternative Sandbox)
Similar to GitHub Codespaces, Gitpod is an ephemeral developer environment platform.

### The Free Tier
Gitpod provides 50 hours per month of free standard workspace usage (up to 4 cores and 8GB RAM). It provides full root access and native Docker execution. If you exhaust your Codespaces allowance, you can instantly pivot your agent's SSH target to a Gitpod workspace to continue benchmarking.

### Step 1: Start a Gitpod Workspace
Spin up a workspace from the Gitpod dashboard. Once inside, grab the remote SSH connection string provided by the Gitpod CLI.

### Step 2: Set DOCKER_HOST
```bash
export DOCKER_HOST="ssh://workspace-id@workspace-host.gitpod.io"
```
And execute the benchmark using our wrapper script!
