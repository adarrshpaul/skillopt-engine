---
name: strict_json_output
constraint: Always respond with valid JSON objects. Never wrap output in markdown code fences. Never include explanatory text outside the JSON.
---
# Strict JSON Output
When generating any output, always produce raw valid JSON without wrapping in ```json``` blocks.
The response must be parseable by `json.loads()` directly.
