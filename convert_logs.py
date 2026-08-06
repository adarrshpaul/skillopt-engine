#!/usr/bin/env python3
import glob
import json
import os
import uuid
import re

def slugify(project):
    normalized = os.path.abspath(os.path.expanduser(project))
    return re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-")

WORKSPACE = "/Users/adarrsh/workspace"
CURSOR_DIR = os.path.expanduser(f"~/.cursor/projects/{slugify(WORKSPACE)}/agent-transcripts")
ANTIGRAVITY_BRAIN = os.path.expanduser("~/.gemini/antigravity/brain")

def run():
    print("Adapting Antigravity transcripts for SkillOpt...")
    if not os.path.exists(ANTIGRAVITY_BRAIN):
        print("No Antigravity brain found.")
        return
        
    os.makedirs(CURSOR_DIR, exist_ok=True)
    
    # We want to link the workspace to the cursor dir for SkillOpt to know the project path
    trust_file = os.path.join(os.path.dirname(CURSOR_DIR), ".workspace-trusted")
    os.makedirs(os.path.dirname(trust_file), exist_ok=True)
    with open(trust_file, "w") as f:
        json.dump({"workspacePath": WORKSPACE}, f)
        
    count = 0
    for conv_dir in os.listdir(ANTIGRAVITY_BRAIN):
        log_file = os.path.join(ANTIGRAVITY_BRAIN, conv_dir, ".system_generated", "logs", "transcript_full.jsonl")
        if not os.path.exists(log_file):
            continue
            
        # Ensure we don't process it twice by keeping track or just overwriting. We'll just overwrite.
        session_id = conv_dir
        out_session_dir = os.path.join(CURSOR_DIR, session_id)
        os.makedirs(out_session_dir, exist_ok=True)
        out_file = os.path.join(out_session_dir, f"{session_id}.jsonl")
        
        # Check if out_file is newer than log_file
        if os.path.exists(out_file) and os.path.getmtime(out_file) >= os.path.getmtime(log_file):
            continue
            
        cursor_lines = []
        try:
            with open(log_file, "r") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        typ = record.get("type")
                        if typ == "USER_INPUT":
                            cursor_lines.append({
                                "role": "user",
                                "message": {
                                    "role": "user",
                                    "content": record.get("content", "")
                                }
                            })
                        elif typ == "PLANNER_RESPONSE":
                            content = []
                            if record.get("content"):
                                content.append({"type": "text", "text": record.get("content")})
                            for tool in record.get("tool_calls", []):
                                content.append({"type": "tool_use", "name": tool.get("toolName", "unknown")})
                                
                            cursor_lines.append({
                                "role": "assistant",
                                "message": {
                                    "role": "assistant",
                                    "content": content
                                }
                            })
                    except Exception:
                        pass
        except Exception:
            pass
            
        if cursor_lines:
            with open(out_file, "w") as f:
                for cl in cursor_lines:
                    f.write(json.dumps(cl) + "\n")
            
            # Match mtime
            mtime = os.path.getmtime(log_file)
            os.utime(out_file, (mtime, mtime))
            count += 1
            
    print(f"Adapted {count} new Antigravity sessions into Cursor format.")

if __name__ == "__main__":
    run()
