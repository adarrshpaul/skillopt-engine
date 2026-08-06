import json
import random
import os

def generate_orchestration_examples():
    examples = []
    
    # We will generate synthetic bash execution tasks
    tasks = [
        ("Deploy a nodejs container.", "docker run -d -p 8080:8080 node:18"),
        ("Install requirements from requirements.txt", "pip install -r requirements.txt"),
        ("Clone the repo and checkout main", "git clone https://github.com/example/repo.git\ncd repo\ngit checkout main"),
        ("Start the postgres database locally", "pg_ctl -D /usr/local/var/postgres start"),
        ("Run the database migrations using alembic", "alembic upgrade head"),
        ("Compile the typescript project", "npx tsc"),
        ("Set up a python virtual environment", "python3 -m venv venv\nsource venv/bin/activate"),
        ("Build the docker image", "docker build -t myapp:latest .")
    ]
    
    for i in range(15):
        for prompt, bash in tasks:
            # Gemma 4 Chat template format
            text = f"<start_of_turn>system\nYou are an execution orchestrator. Always output raw bash code blocks. Do not use conversational filler.<end_of_turn>\n<start_of_turn>user\n{prompt}<end_of_turn>\n<start_of_turn>model\n```bash\n{bash}\n```<end_of_turn>"
            
            examples.append({"text": text})
            
    random.shuffle(examples)
    return examples

def main():
    data = generate_orchestration_examples()
    
    split_idx = int(len(data) * 0.9)
    train_data = data[:split_idx]
    valid_data = data[split_idx:]
    
    os.makedirs("/Users/adarrsh/workspace/data/gemma", exist_ok=True)
    
    with open("/Users/adarrsh/workspace/data/gemma/train.jsonl", "w") as f:
        for d in train_data:
            f.write(json.dumps(d) + "\n")
            
    with open("/Users/adarrsh/workspace/data/gemma/valid.jsonl", "w") as f:
        for d in valid_data:
            f.write(json.dumps(d) + "\n")
            
    print(f"Generated {len(train_data)} training examples and {len(valid_data)} validation examples.")

if __name__ == "__main__":
    main()
