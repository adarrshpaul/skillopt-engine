#!/bin/bash
# SkillOpt Engine — System Validation Script
# Inspired by Claude Code Harness validate-plugin.sh
# Checks that all components are wired, files exist, and services respond.

set -euo pipefail

PASS=0
FAIL=0
WARN=0

pass() { echo "  ✅ $1"; PASS=$((PASS+1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }
warn() { echo "  ⚠️  $1"; WARN=$((WARN+1)); }

echo "=========================================="
echo " SkillOpt Engine — System Validation"
echo "=========================================="
echo ""

# 1. Core Files
echo "1. Core File Existence"
echo "------------------------------------------"
for f in model_router.py contracts.py master_cockpit.py admission_controller_grpc.py \
         graph_store.py p2_worker_stub.py p3_faiss_worker.py graph_api_server.py \
         orchestrator.py static/index.html static/tester.html start_mlx_fleet.sh \
         proto/admission.proto proto/worker.proto Makefile; do
    if [ -f "/Users/adarrsh/workspace/$f" ]; then
        pass "$f exists"
    else
        fail "$f MISSING"
    fi
done
echo ""

# 2. Python Import Check
echo "2. Python Import Validation"
echo "------------------------------------------"
PYTHON="/Users/adarrsh/workspace/ml-env-311/bin/python"
for mod in model_router contracts graph_store; do
    if $PYTHON -c "import $mod" 2>/dev/null; then
        pass "import $mod OK"
    else
        fail "import $mod FAILED"
    fi
done
echo ""

# 3. Service Health (non-blocking)
echo "3. Service Health Checks"
echo "------------------------------------------"
for port_label in "8800:Ornith-9B" "8801:Ling-3.0" "8802:Nanbeige-3B" "5002:MasterCockpit" "50051:AdmissionGRPC"; do
    port=$(echo $port_label | cut -d: -f1)
    label=$(echo $port_label | cut -d: -f2)
    if lsof -i:$port -sTCP:LISTEN >/dev/null 2>&1; then
        pass "$label on :$port is LIVE"
    else
        warn "$label on :$port is DOWN"
    fi
done
echo ""

# 4. API Contract Validation
echo "4. API Contract Validation"
echo "------------------------------------------"
if curl -sf http://localhost:5002/api/fleet >/dev/null 2>&1; then
    # Verify fleet has required roles
    FLEET=$(curl -sf http://localhost:5002/api/fleet)
    for role in planner reviewer coder fallback; do
        if echo "$FLEET" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '$role' in d.get('roles',{})" 2>/dev/null; then
            pass "/api/fleet has role '$role'"
        else
            fail "/api/fleet missing role '$role'"
        fi
    done
    # Verify port isolation
    CODER_URL=$(echo "$FLEET" | python3 -c "import sys,json; print(json.load(sys.stdin)['roles']['coder']['url'])" 2>/dev/null)
    PLANNER_URL=$(echo "$FLEET" | python3 -c "import sys,json; print(json.load(sys.stdin)['roles']['planner']['url'])" 2>/dev/null)
    if echo "$CODER_URL" | grep -q ":8800" && echo "$PLANNER_URL" | grep -q ":8801"; then
        pass "Port isolation: coder→:8800, planner→:8801"
    else
        fail "Port isolation BROKEN: coder=$CODER_URL, planner=$PLANNER_URL"
    fi
else
    warn "/api/fleet not reachable (Master Cockpit may be down)"
fi

if curl -sf http://localhost:5002/api/telemetry >/dev/null 2>&1; then
    TELEM=$(curl -sf http://localhost:5002/api/telemetry)
    for key in p1_tokens p2_queue_length p3_pending_jobs total_preemptions; do
        if echo "$TELEM" | python3 -c "import sys,json; d=json.load(sys.stdin); assert '$key' in d" 2>/dev/null; then
            pass "/api/telemetry has '$key'"
        else
            fail "/api/telemetry missing '$key'"
        fi
    done
else
    warn "/api/telemetry not reachable"
fi
echo ""

# 5. Test Suite
echo "5. Unit Test Suite"
echo "------------------------------------------"
if [ -d "/Users/adarrsh/workspace/tests" ]; then
    TEST_COUNT=$(find /Users/adarrsh/workspace/tests -name 'test_*.py' | wc -l | tr -d ' ')
    pass "$TEST_COUNT test files found"
else
    fail "tests/ directory missing"
fi
echo ""

# 6. Schema Files
echo "6. Schema Validation Files"
echo "------------------------------------------"
for schema in chat_response.json fleet_response.json telemetry_response.json; do
    if [ -f "/Users/adarrsh/workspace/tests/schemas/$schema" ]; then
        pass "Schema: $schema exists"
    else
        warn "Schema: $schema missing"
    fi
done
echo ""

# 7. Fixtures
echo "7. Test Fixtures"
echo "------------------------------------------"
FIX_COUNT=$(find /Users/adarrsh/workspace/tests/fixtures -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
if [ "$FIX_COUNT" -gt 0 ]; then
    pass "$FIX_COUNT fixture files found"
else
    warn "No fixture files found"
fi
echo ""

# Summary
echo "=========================================="
echo " RESULTS"
echo "=========================================="
echo "  ✅ Passed:  $PASS"
echo "  ⚠️  Warnings: $WARN"
echo "  ❌ Failed:  $FAIL"
echo ""
if [ $FAIL -eq 0 ]; then
    echo "  ✅ System validation PASSED"
    exit 0
else
    echo "  ❌ System validation FAILED"
    exit 1
fi
