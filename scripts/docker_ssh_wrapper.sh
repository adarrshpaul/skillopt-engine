#!/bin/bash
if [ "$1" = "compose" ]; then
    shift
    
    # We must rewrite any arguments that reference the local workspace path
    # to reference the remote Codespace path.
    # Example: -f /Users/adarrsh/workspace/ABC-Bench-Dataset/... -> -f /workspaces/skillopt-engine/ABC-Bench-Dataset/...
    
    ARGS=()
    for arg in "$@"; do
        # Replace the local path prefix with the remote one
        # Use dynamic pwd to replace
        WORKSPACE_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
        rewritten_arg="${arg//$WORKSPACE_ROOT/\/workspaces\/skillopt-engine}"
        ARGS+=("$rewritten_arg")
    done

    # Determine the remote directory by replacing the local pwd
    WORKSPACE_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
    REMOTE_DIR=$(pwd | sed "s|$WORKSPACE_ROOT|/workspaces/skillopt-engine|g")
    
    # Run the command over SSH (extracting hostname from DOCKER_HOST, default to codespace)
    SSH_TARGET=$(echo "$DOCKER_HOST" | sed 's|ssh://||g')
    if [ -z "$SSH_TARGET" ]; then
        echo "ERROR: DOCKER_HOST is not set for ssh wrapper!"
        exit 1
    fi
    ssh -o StrictHostKeyChecking=accept-new "$SSH_TARGET" "cd \"$REMOTE_DIR\" && docker compose ${ARGS[*]}"
else
    # Any other docker command just fails because we only intercept compose
    echo "ERROR: Native docker is not installed. This wrapper only supports 'docker compose'."
    exit 1
fi
