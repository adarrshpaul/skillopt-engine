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
        LOCAL_PREFIX="/Users/adarrsh/workspace"
        REMOTE_PREFIX="/workspaces/skillopt-engine"
        rewritten_arg="${arg//$LOCAL_PREFIX/$REMOTE_PREFIX}"
        ARGS+=("$rewritten_arg")
    done

    WORKSPACE_ROOT="/Users/adarrsh/workspace"
    CURRENT_DIR=$(pwd)
    echo "DEBUG PWD: $CURRENT_DIR" >&2
    REMOTE_DIR=$(echo "$CURRENT_DIR" | sed "s|$WORKSPACE_ROOT|/workspaces/skillopt-engine|g")
    echo "DEBUG REMOTE_DIR: $REMOTE_DIR" >&2
    
    # Run the command over SSH (extracting hostname from DOCKER_HOST, default to codespace)
    SSH_TARGET=$(echo "$DOCKER_HOST" | sed 's|ssh://||g')
    if [ -z "$SSH_TARGET" ]; then
        echo "ERROR: DOCKER_HOST is not set for ssh wrapper!"
        exit 1
    fi
    env > /tmp/docker_ssh_wrapper_env.txt
    
    # Forward T_BENCH_ environment variables to remote host
    ENV_VARS=""
    for var in $(env | grep "^T_BENCH_"); do
        ENV_VARS="$ENV_VARS $var"
    done
    echo "DEBUG ENV_VARS: '$ENV_VARS'" >&2

    ssh -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=15 -o ServerAliveCountMax=120 "$SSH_TARGET" "cd \"$REMOTE_DIR\" && env $ENV_VARS docker compose ${ARGS[*]}"
else
    # Any other docker command just fails because we only intercept compose
    echo "ERROR: Native docker is not installed. This wrapper only supports 'docker compose'."
    exit 1
fi
