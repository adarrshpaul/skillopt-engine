#!/bin/bash
source /Users/adarrsh/workspace/tb-env/bin/activate

echo "========================================="
echo "Running Test 1: Local LLM Mode (Ornith 9B via Ollama)"
echo "========================================="

# export PLANNER_ENGINE="ollama"
# export PLANNER_URL="http://localhost:11434"
# export PLANNER_MODEL="ornith9b"

# export REVIEWER_ENGINE="ollama"
# export REVIEWER_URL="http://localhost:11434"
# export REVIEWER_MODEL="ornith9b"

# export CODER_ENGINE="ollama"
# export CODER_URL="http://localhost:11434"
# export CODER_MODEL="ornith9b"

# python3 -u orchestrator.py "Create a math_helper.py file that adds two numbers"

echo "========================================="
echo "Running Test 2: API Mode (OpenRouter)"
echo "========================================="

export PLANNER_ENGINE="openrouter"
export PLANNER_URL="https://openrouter.ai/api/v1"
export PLANNER_MODEL="nvidia/nemotron-3-ultra-550b-a55b:free"

export REVIEWER_ENGINE="openrouter"
export REVIEWER_URL="https://openrouter.ai/api/v1"
export REVIEWER_MODEL="nvidia/nemotron-3-super-120b-a12b:free"

export CODER_ENGINE="openrouter"
export CODER_URL="https://openrouter.ai/api/v1"
export CODER_MODEL="poolside/laguna-s-2.1:free"

python3 -u orchestrator.py "Create a robust Python CLI application in taskmaster.py that manages a todo list saved to tasks.json. It must support add, list, and complete arguments via argparse. Then, write a complete pytest test suite in test_taskmaster.py to verify it works."
