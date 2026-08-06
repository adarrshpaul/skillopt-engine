import json
import random
import os

def generate_code_examples():
    examples = []
    
    # We will generate synthetic Python coding tasks
    tasks = [
        ("Write a Python function to reverse a string.", "def reverse_string(s):\n    return s[::-1]"),
        ("Write a Python script that calculates the factorial of a number.", "def factorial(n):\n    if n == 0:\n        return 1\n    return n * factorial(n - 1)"),
        ("Create a function that checks if a string is a palindrome.", "def is_palindrome(s):\n    return s == s[::-1]"),
        ("Write a Python function that sorts a list of integers using bubble sort.", "def bubble_sort(arr):\n    n = len(arr)\n    for i in range(n):\n        for j in range(0, n-i-1):\n            if arr[j] > arr[j+1]:\n                arr[j], arr[j+1] = arr[j+1], arr[j]\n    return arr"),
        ("Write a Python function to find the maximum element in a list.", "def find_max(arr):\n    if not arr:\n        return None\n    max_val = arr[0]\n    for val in arr:\n        if val > max_val:\n            max_val = val\n    return max_val"),
        ("Create a generator that yields the Fibonacci sequence.", "def fibonacci_gen():\n    a, b = 0, 1\n    while True:\n        yield a\n        a, b = b, a + b"),
        ("Write a Python class representing a Bank Account with deposit and withdraw methods.", "class BankAccount:\n    def __init__(self, balance=0):\n        self.balance = balance\n\n    def deposit(self, amount):\n        self.balance += amount\n\n    def withdraw(self, amount):\n        if amount > self.balance:\n            raise ValueError('Insufficient funds')\n        self.balance -= amount"),
        ("Write a python function to merge two dictionaries.", "def merge_dicts(d1, d2):\n    merged = d1.copy()\n    merged.update(d2)\n    return merged")
    ]
    
    # Duplicate and mutate slightly to get ~100 examples
    for i in range(15):
        for prompt, code in tasks:
            # We want the model to learn to output EXACTLY the code block.
            # We use the standard instruction format (this depends on the base model, 
            # but deepreinforce-ai/Ornith typically uses Qwen format: <|im_start|>user ... <|im_end|>)
            
            # For mlx_lm, the simplest and most robust way is to just format the text string 
            # using the model's expected prompt template.
            text = f"<|im_start|>system\nYou are a coding agent. Always output raw code blocks. Do not use conversational filler.<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n```python\n{code}\n```<|im_end|>"
            
            examples.append({"text": text})
            
    random.shuffle(examples)
    return examples

def main():
    data = generate_code_examples()
    
    # 90% train, 10% valid
    split_idx = int(len(data) * 0.9)
    train_data = data[:split_idx]
    valid_data = data[split_idx:]
    
    os.makedirs("/Users/adarrsh/workspace/data", exist_ok=True)
    
    with open("/Users/adarrsh/workspace/data/train.jsonl", "w") as f:
        for d in train_data:
            f.write(json.dumps(d) + "\n")
            
    with open("/Users/adarrsh/workspace/data/valid.jsonl", "w") as f:
        for d in valid_data:
            f.write(json.dumps(d) + "\n")
            
    print(f"Generated {len(train_data)} training examples and {len(valid_data)} validation examples.")

if __name__ == "__main__":
    main()
