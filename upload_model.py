import os
from huggingface_hub import HfApi

def main():
    token = os.environ.get("HF_TOKEN", "")
    repo_id = "adarrsh/ornith-gemma-2-9b"
    
    api = HfApi(token=token)
    
    print(f"Creating repo {repo_id} (if it doesn't exist)...")
    try:
        api.create_repo(repo_id=repo_id, exist_ok=True, repo_type="model")
    except Exception as e:
        print(f"Failed to create repo: {e}")
        # Proceed anyway in case it already exists but we don't have create permissions 
        # (though write permissions usually imply create)

    print(f"Uploading fused MLX weights to {repo_id}...")
    api.upload_folder(
        folder_path="/Users/adarrsh/workspace/models/fused-gemma",
        repo_id=repo_id,
        repo_type="model",
    )
    print("Upload complete! Model is now live on Hugging Face.")

if __name__ == "__main__":
    main()
