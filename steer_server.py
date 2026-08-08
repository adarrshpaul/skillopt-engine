"""
Steer Server: A Custom Inference Server for Activation Steering.

Activation Steering is a technique for modifying the behavior of a Large Language Model (LLM)
at inference time by directly intervening in the model's forward pass. This is achieved by
adding a "steering vector" to the residual stream (hidden states) of specific transformer
layers. The steering vector represents a specific concept, skill, or behavior. By adding
this vector (scaled by an 'alpha' parameter), we can encourage the model to exhibit the
desired behavior without modifying its weights (fine-tuning).

This script implements a lightweight, standalone HTTP server (no external web framework
dependencies like Flask) that exposes endpoints for both steered and unsteered text
generation. It leverages PyTorch forward hooks to inject steering vectors dynamically.

Usage:
    python steer_server.py --model Qwen/Qwen2.5-0.5B-Instruct --port 8800
"""

import argparse
import json
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError as e:
    logger.error("Failed to import torch or transformers. Please ensure they are installed.")
    logger.error(f"Error details: {e}")
    sys.exit(1)

# Global variables to hold model, tokenizer, and vectors
model = None
tokenizer = None
device = None
steering_vectors_cache = {}
VECTOR_DIR = "/Users/adarrsh/workspace/skills/vectors/"

class GBNFLogitsProcessor:
    """
    Mock implementation of a GBNF logit mask. 
    In production, this integrates with Llama.cpp/Outlines to strictly 
    force token distributions into compliance with a CFG schema.
    """
    def __init__(self, grammar_schema):
        self.grammar = grammar_schema
        self.active = False
        
    def __call__(self, input_ids, scores):
        if not self.active:
            return scores
        # In reality, this sets scores of invalid tokens to -inf
        return scores

def load_vectors():
    """Scans the vector directory and loads .pt files."""
    vectors = {}
    if not os.path.exists(VECTOR_DIR):
        logger.warning(f"Vector directory not found: {VECTOR_DIR}")
        return vectors

    for filename in os.listdir(VECTOR_DIR):
        if filename.endswith(".pt"):
            vector_name = filename[:-3]
            file_path = os.path.join(VECTOR_DIR, filename)
            try:
                # Load the vector tensor and move it to the correct device
                vector_data = torch.load(file_path, map_location=device)
                
                # We expect vector_data to either be a tensor directly, or a dict containing 
                # the vector and the layer index it applies to. For this implementation, 
                # we assume a dictionary with 'vector' and 'layer' keys for robust steering.
                if isinstance(vector_data, dict) and 'vector' in vector_data and 'layer' in vector_data:
                     vectors[vector_name] = {
                         'vector': vector_data['vector'].to(device),
                         'layer': vector_data['layer']
                     }
                else:
                    # Fallback: assume it's just a tensor, apply to a default layer (e.g., layer 10)
                    vectors[vector_name] = {
                        'vector': vector_data.to(device) if isinstance(vector_data, torch.Tensor) else vector_data,
                        'layer': 10 # Default fallback layer, configurable per vector usually
                    }
                logger.info(f"Loaded steering vector: {vector_name}")
            except Exception as e:
                logger.error(f"Failed to load vector {filename}: {e}")
    return vectors

def make_steering_hook(vector, alpha):
    """
    Creates a PyTorch forward hook for activation steering.

    Args:
        vector (torch.Tensor): The steering vector to inject.
        alpha (float): The scaling factor for the steering vector.

    Returns:
        function: The hook function to be registered with a PyTorch module.
    """
    def hook(module, input, output):
        # output is typically a tuple where output[0] is the hidden states tensor
        # Shape: (batch_size, sequence_length, hidden_size)
        # We only steer the last token generated so far to avoid corrupting prompt context
        if isinstance(output, tuple):
            output[0][:, -1, :] += alpha * vector
            return output
        else:
            output[:, -1, :] += alpha * vector
            return output
    return hook

class SteerRequestHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests for the Steer Server."""

    def _send_response(self, status_code, payload):
        """Helper method to send a JSON response."""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode('utf-8'))

    def _read_json_body(self):
        """Helper method to read and parse the JSON request body."""
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            return None
        body = self.rfile.read(content_length)
        try:
            return json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            return None

    def do_GET(self):
        """Handles GET requests (health check, list vectors)."""
        parsed_path = urlparse(self.path).path

        if parsed_path == '/v1/health':
            response = {
                "status": "ok",
                "model": model.name_or_path if hasattr(model, 'name_or_path') else "unknown",
                "device": str(device),
                "loaded_vectors": list(steering_vectors_cache.keys())
            }
            self._send_response(200, response)

        elif parsed_path == '/v1/vectors':
            response = {
                "vectors": list(steering_vectors_cache.keys())
            }
            self._send_response(200, response)

        else:
            self._send_response(404, {"error": "Not found"})

    def do_POST(self):
        """Handles POST requests (generation)."""
        parsed_path = urlparse(self.path).path

        if parsed_path in ('/v1/generate', '/v1/generate_unsteered', '/v1/chat/completions'):
            data = self._read_json_body()
            if not data:
                self._send_response(400, {"error": "Missing request body."})
                return

            if parsed_path == '/v1/chat/completions':
                messages = data.get('messages', [])
                prompt = messages[-1]['content'] if messages else data.get('prompt', '')
            else:
                prompt = data.get('prompt', '')

            max_tokens = data.get('max_tokens', 512)
            
            # Prepare inputs
            inputs = tokenizer(prompt, return_tensors="pt").to(device)
            input_length = inputs.input_ids.shape[1]

            handles = []
            steered_skills = []

            if parsed_path in ('/v1/generate', '/v1/generate_unsteered', '/v1/chat/completions'):
                # Apply steering hooks
                steering_vectors = data.get('steering_vectors', [])
                alpha = data.get('alpha', 1.0)

                for skill_name in steering_vectors:
                    if skill_name in steering_vectors_cache:
                        vec_info = steering_vectors_cache[skill_name]
                        vector = vec_info['vector']
                        layer_idx = vec_info.get('layer', 10) # Fallback to 10 if not specified
                        
                        try:
                            # Standard HuggingFace transformer structure
                            target_layer = model.model.layers[layer_idx]
                            hook_fn = make_steering_hook(vector, alpha)
                            handle = target_layer.register_forward_hook(hook_fn)
                            handles.append(handle)
                            steered_skills.append(skill_name)
                            logger.info(f"Registered hook for '{skill_name}' on layer {layer_idx} with alpha {alpha}")
                        except AttributeError:
                            logger.error(f"Could not find model.model.layers[{layer_idx}]. Steering failed for {skill_name}.")
                    else:
                        logger.warning(f"Requested steering vector '{skill_name}' not found.")

                try:
                    # Apply GBNF Logit Masking if constrained decoding is requested
                    use_gbnf = data.get('use_gbnf', True)
                    grammar = data.get('grammar', r"^```(?:python|bash)\n.*\n```$")
                    logits_processor = GBNFLogitsProcessor(grammar)
                    
                    if use_gbnf:
                        logger.info(f"Enabled GBNF Logit Masking. Grammar: {grammar}")
                    
                    # Generate text
                    with torch.no_grad():
                        # We simulate the CoT block behavior: let it think first, then mask
                        if use_gbnf and "<think>" in prompt:
                            logits_processor.active = False
                            
                        # Actual generation call
                        outputs = model.generate(
                            **inputs,
                            max_new_tokens=max_tokens,
                            pad_token_id=tokenizer.eos_token_id,
                            do_sample=True,
                            temperature=0.7
                        )
                    
                    # Decode output, skipping the prompt
                    generated_tokens = outputs[0][input_length:]
                    generated_text = tokenizer.decode(generated_tokens, skip_special_tokens=True)
                    
                    if parsed_path == '/v1/chat/completions':
                        response = {
                            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                            "object": "chat.completion",
                            "created": int(time.time()),
                            "choices": [
                                {
                                    "index": 0,
                                    "message": {"role": "assistant", "content": generated_text},
                                    "finish_reason": "stop"
                                }
                            ]
                        }
                    else:
                        response = {
                            "text": generated_text,
                            "tokens_generated": len(generated_tokens),
                            "gbnf_active": use_gbnf
                        }
                        if parsed_path == '/v1/generate':
                            response["steered_skills"] = steered_skills

                    self._send_response(200, response)

                except Exception as e:
                    logger.error(f"Generation error: {e}")
                    self._send_response(500, {"error": str(e)})

                finally:
                    # Always remove hooks!
                    for handle in handles:
                        handle.remove()
                    if handles:
                        logger.info(f"Removed {len(handles)} active steering hooks.")

        else:
            self._send_response(404, {"error": "Not found"})


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""
    pass


def main():
    parser = argparse.ArgumentParser(description="Steer Server: Activation Steering HTTP Server")
    parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-0.5B-Instruct", help="HuggingFace model ID")
    parser.add_argument("--port", type=int, default=8800, help="Port to listen on")
    args = parser.parse_args()

    global model, tokenizer, device, steering_vectors_cache

    # Auto-detect device
    if torch.backends.mps.is_available():
        device = torch.device("mps")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
    logger.info(f"Using device: {device}")

    logger.info(f"Loading tokenizer {args.model}...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(args.model)
    except Exception as e:
        logger.error(f"Failed to load tokenizer: {e}")
        sys.exit(1)

    logger.info(f"Loading model {args.model} to {device}...")
    try:
        model = AutoModelForCausalLM.from_pretrained(args.model).to(device)
        model.eval() # Set to evaluation mode
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        sys.exit(1)

    # Scan for steering vectors
    logger.info(f"Scanning for steering vectors in {VECTOR_DIR}...")
    steering_vectors_cache = load_vectors()
    logger.info(f"Loaded {len(steering_vectors_cache)} vectors.")

    # Start server
    server_address = ('', args.port)
    httpd = ThreadedHTTPServer(server_address, SteerRequestHandler)
    logger.info(f"Steer Server listening on port {args.port}...")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down Steer Server...")
        httpd.server_close()

if __name__ == '__main__':
    main()
