import sys
import os

class ModelValidator:
    """
    Validates model compatibility and hardware constraints pre-flight.
    Ensures we don't start a 300-instance run if the MLX architecture 
    is fundamentally incompatible with the chosen model.
    """
    
    @staticmethod
    def validate_mlx_compatibility(model_id: str) -> bool:
        """
        Attempts a dry-run load of the model architecture to verify
        that stock mlx-lm actually supports it.
        """
        print(f"🔍 [Pre-Flight] Verifying architecture compatibility for {model_id}...", flush=True)
        try:
            import mlx.core as mx
            from mlx_lm import load
            
            # Enforce strict 8GB memory caps to prevent kernel panics
            if hasattr(mx, 'set_wired_limit'): 
                mx.set_wired_limit(8 * 1024 * 1024 * 1024)
                mx.set_cache_limit(8 * 1024 * 1024 * 1024)
            else:
                mx.metal.set_wired_limit(8 * 1024 * 1024 * 1024)
                mx.metal.set_cache_limit(8 * 1024 * 1024 * 1024)
                
            # Attempt load. If the architecture is unknown, mlx_lm raises ValueError or KeyError
            # before it finishes loading the gigabytes of tensors.
            model, _ = load(model_id, tokenizer_config={"trust_remote_code": True})
            
            # Clean up immediately
            del model
            import gc
            gc.collect()
            mx.metal.clear_cache()
            
            print(f"✅ [Pre-Flight] Model {model_id} architecture is natively supported by MLX.", flush=True)
            return True
            
        except Exception as e:
            print(f"❌ [Pre-Flight] FATAL: Model {model_id} is INCOMPATIBLE with the current MLX runtime.\nReason: {e}", flush=True)
            return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        ModelValidator.validate_mlx_compatibility(sys.argv[1])
    else:
        print("Usage: python model_validator.py <model_id>")
