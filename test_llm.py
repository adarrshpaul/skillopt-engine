import litellm

response = litellm.completion(
    model="openai/default",
    messages=[{"role": "user", "content": "Hello"}],
    api_base="http://localhost:8801/v1",
    api_key="sk-mock"
)
print(response)
