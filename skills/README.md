# Steerable Skills

This directory contains markdown skill definitions that can be compiled into **Instruction Vectors** for activation steering.

## Skill File Format

Each skill is a markdown file with YAML-like frontmatter:

```markdown
---
name: skill_name
constraint: A single-sentence description of the constraint to enforce.
---
# Human-Readable Title
Detailed description of the skill behavior.
```

## Workflow

### 1. Write a Skill
Create a `.md` file in this directory following the format above.

### 2. Compile the Skill
```bash
python steer_compile.py --skill skills/your_skill.md --model Qwen/Qwen2.5-0.5B-Instruct
```
This generates a `.pt` file in `skills/vectors/` containing the pre-computed instruction vector.

### 3. Use at Inference
The `steer_server.py` inference server automatically loads all compiled vectors from `skills/vectors/`. Request steering by name:
```bash
curl -X POST http://localhost:8800/v1/generate \
  -d '{"prompt": "Write a greeting", "steering_vectors": ["strict_json_output"], "alpha": 1.5}'
```

### 4. Compose Multiple Skills
You can apply multiple steering vectors simultaneously:
```json
{"steering_vectors": ["strict_json_output", "concise_response"]}
```
Vectors are added to the residual stream independently, enabling compositional constraint enforcement.

## Available Skills

| Skill | Constraint |
|---|---|
| `strict_json` | Forces valid JSON output without markdown fences |
| `concise_response` | Limits responses to under 100 words |
| `no_apologies` | Removes apologetic language |
| `code_only` | Outputs only code, no explanations |
