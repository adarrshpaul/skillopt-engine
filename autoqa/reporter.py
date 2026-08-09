"""Reporting and Telemetry module for QA Harness."""
import json
import os
from typing import List, Dict, Any

class QAReporter:
    def __init__(self):
        self.results: List[Dict[str, Any]] = []

    def record_result(self, test_name: str, status: str, failure_type: str = None, memory_metrics: Dict[str, Any] = None, trajectory: List[Dict[str, Any]] = None):
        """
        Record a test result.
        failure_type: 'infra_error' or 'semantic_fail'
        """
        self.results.append({
            "test_name": test_name,
            "status": status,
            "failure_type": failure_type,
            "memory": memory_metrics or {},
            "trajectory": trajectory
        })

    def generate_allure_report(self):
        """Generate static HTML / Allure formatted JSONs."""
        # Scaffold
        pass

    def pipe_to_dpo(self, dpo_logs_path="dpo_logs.jsonl"):
        """Pipe only semantic failures to DPO log, deduping signatures."""
        seen_signatures = set()
        for res in self.results:
            if res["status"] == "FAIL" and res["failure_type"] == "semantic_fail":
                # Create a signature (e.g., hash of the last action or error)
                sig, sig_type = self._generate_signature(res["trajectory"])
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    
                    # Annotate the result with the signature type
                    log_entry = res.copy()
                    log_entry["_dpo_metadata"] = {"signature_type": sig_type, "signature_hash": sig}
                    
                    self._append_to_jsonl(dpo_logs_path, log_entry)
    
    def _generate_signature(self, trajectory):
        if not trajectory:
            return "empty", "empty"
        import re
        import hashlib
        
        last_step = trajectory[-1] if isinstance(trajectory, list) else trajectory
        error = last_step.get("error", "") if isinstance(last_step, dict) else str(last_step)
        
        step_id = last_step.get("step_id", "unknown") if isinstance(last_step, dict) else "unknown"
        prompt = last_step.get("prompt", "") if isinstance(last_step, dict) else ""
        tool_call = "no_tool"
        if "<execute>" in prompt:
            tool_call = prompt.split("<execute>")[1].split("</execute>")[0].strip().split("(")[0]
            
        # Try to find an Exception class name (e.g., 'ValueError:')
        match = re.search(r'([A-Za-z0-9_]+Error):', error)
        if match:
            error_key = match.group(1)
            sig_type = "structural_exception"
        else:
            # Fallback: Regex normalize the error message to strip specifics
            norm = error
            norm = re.sub(r'0x[0-9a-fA-F]+', '<HEX>', norm)
            norm = re.sub(r'\b[0-9a-f]{8}\b-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-\b[0-9a-f]{12}\b', '<UUID>', norm)
            norm = re.sub(r'\b\d+\b', '<NUM>', norm)
            norm = re.sub(r'/[a-zA-Z0-9_./-]+', '<PATH>', norm)
            error_key = hashlib.sha256(norm.encode('utf-8')).hexdigest()
            sig_type = "unstructured_crash"
            
        # Return deterministic structural hash
        key = f"{error_key}_{step_id}_{tool_call}"
        return hashlib.sha256(key.encode('utf-8')).hexdigest(), sig_type

    def _append_to_jsonl(self, path, data):
        with open(path, "a") as f:
            f.write(json.dumps(data) + "\n")
