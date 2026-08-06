import json
import os

def main():
    benchmark_file = "/Users/adarrsh/workspace/benchmark_tasks.jsonl"
    
    tasks = []
    
    # --- 10 Orchestration Tasks ---
    orchestration_prompts = [
        "Deploy a Node.js express backend and a React frontend on ports 8080 and 3000.",
        "Create a bash script to clone a GitHub repository, build the Docker image, and run it.",
        "Write a script to back up a PostgreSQL database and upload it to an S3 bucket.",
        "Set up an Nginx reverse proxy routing traffic to two different local ports.",
        "Create a script that monitors CPU usage and sends a Slack alert if it exceeds 90%.",
        "Deploy a Python FastAPI app using Gunicorn and Uvicorn workers.",
        "Automate the installation and configuration of Redis on an Ubuntu server.",
        "Write a CI/CD bash script that runs pytest and builds a wheel file if tests pass.",
        "Create a script to parse Apache logs and ban IPs with too many 404 requests using iptables.",
        "Set up a local Kubernetes cluster using Minikube and deploy a simple pod."
    ]
    for i, p in enumerate(orchestration_prompts):
        tasks.append({
            "task_id": f"ORCH-{i+1}",
            "type": "orchestration",
            "prompt": p,
            "expected_format": "bash"
        })

    # --- 10 Coding Tasks ---
    coding_prompts = [
        "Write a Python function to perform a binary search on a sorted array.",
        "Create a React component that fetches user data from an API and displays it in a table.",
        "Write a JavaScript function to debounce rapid consecutive button clicks.",
        "Implement a thread-safe Singleton design pattern in Python.",
        "Create a Node.js Express route that accepts file uploads and saves them to disk.",
        "Write a Python script that parses a CSV file and converts it into a SQLite database.",
        "Implement a breadth-first search algorithm for a graph represented as an adjacency list.",
        "Create a React Hook that tracks the mouse position on the screen.",
        "Write a Python function to calculate the Levenshtein distance between two strings.",
        "Implement a rate limiter in Node.js using Redis."
    ]
    for i, p in enumerate(coding_prompts):
        tasks.append({
            "task_id": f"CODE-{i+1}",
            "type": "coding",
            "prompt": p,
            "expected_format": "code"
        })

    with open(benchmark_file, "w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t) + "\n")
            
    print(f"Generated {len(tasks)} benchmark tasks to {benchmark_file}")

if __name__ == "__main__":
    main()
