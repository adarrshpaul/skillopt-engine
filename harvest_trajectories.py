import json
import argparse
import pathlib
import re

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Harvest high-quality trajectories from transcript.")
    parser.add_argument(
        "--transcript",
        type=str,
        default="/Users/adarrsh/.gemini/antigravity/brain/a4b88bab-7147-4abc-9b32-397be8142f00/.system_generated/logs/transcript_full.jsonl",
        help="Path to the transcript JSONL file."
    )
    parser.add_argument(
        "--output",
        type=str,
        default="/Users/adarrsh/workspace/dataset.jsonl",
        help="Path to the output dataset JSONL file."
    )
    return parser.parse_args()

def extract_trajectories(transcript_path, output_path):
    """
    Extract high-quality (prompt, response) pairs from the given transcript.
    
    Reads the JSONL transcript line by line. Looks for consecutive pairs of
    USER_INPUT and PLANNER_RESPONSE. Filters them based on quality criteria
    and writes the extracted data to the output JSONL file.
    
    Args:
        transcript_path (str): Path to input transcript.
        output_path (str): Path to output dataset.
    """
    transcript_file = pathlib.Path(transcript_path)
    if not transcript_file.exists():
        print(f"Error: Transcript file not found at {transcript_path}")
        return
    
    output_file = pathlib.Path(output_path)
    
    total_pairs = 0
    filtered_pairs = 0
    total_response_length = 0
    
    # Read all lines
    lines = []
    with open(transcript_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                    
    # Find consecutive (USER_INPUT, PLANNER_RESPONSE) pairs
    dataset = []
    
    # Sort lines by step_index just in case, though they should be sequential
    # Assuming step_index is available
    lines.sort(key=lambda x: x.get("step_index", 0))
    
    for i in range(len(lines) - 1):
        current_step = lines[i]
        next_step = lines[i+1]
        
        if current_step.get("type") == "USER_INPUT" and next_step.get("type") == "PLANNER_RESPONSE":
            total_pairs += 1
            
            prompt_content = current_step.get("content", "")
            response_content = next_step.get("content", "")
            status = next_step.get("status", "")
            tool_calls = next_step.get("tool_calls", [])
            
            # Filtering criteria
            if status == "ERROR":
                continue
            if not response_content or len(response_content) < 50:
                continue

            
            # Extract features
            extracted_tool_calls = []
            if tool_calls:
                for tc in tool_calls:
                    if isinstance(tc, dict) and "name" in tc:
                        extracted_tool_calls.append(tc["name"])
                    elif isinstance(tc, str):
                        extracted_tool_calls.append(tc)
                        
            # Check for code blocks
            has_code = bool(re.search(r"```[\s\S]*?```", response_content))
            response_length = len(response_content)
            
            pair = {
                "prompt": prompt_content,
                "response": response_content,
                "tool_calls": extracted_tool_calls,
                "has_code": has_code,
                "response_length": response_length
            }
            dataset.append(pair)
            
            filtered_pairs += 1
            total_response_length += response_length
            
    # Output to file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item) + "\n")
            
    avg_length = total_response_length / filtered_pairs if filtered_pairs > 0 else 0
    
    print("--- Summary ---")
    print(f"Total pairs found: {total_pairs}")
    print(f"Pairs after filtering: {filtered_pairs}")
    print(f"Average response length: {avg_length:.2f} chars")

if __name__ == "__main__":
    args = parse_args()
    extract_trajectories(args.transcript, args.output)
