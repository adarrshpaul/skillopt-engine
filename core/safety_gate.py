"""
Two-tier pre-execution safety gate.
Layer 1: Runtime Hard Floors (non-overridable, no config bypass).
Layer 2: Configurable Guardrails (deny / ask / warn per project config).
Inspired by Claude Code Harness R01-R15 + DeepSeek Harness monotonic guards.
"""
import re
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Callable
from enum import Enum
from contracts import ToolGuard, GuardDecision, GuardContext

class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"
    WARN = "warn"

@dataclass
class GuardResult:
    decision: Decision
    rule_id: str = ""
    reason: str = ""

    def to_guard_decision(self) -> GuardDecision:
        return GuardDecision(
            decision=self.decision.value,
            rule_id=self.rule_id,
            reason=self.reason
        )


# ═══════════════════════════════════════════════════════════
# LAYER 1: RUNTIME HARD FLOORS (Zero override switches)
# ═══════════════════════════════════════════════════════════

BILLING_PATTERNS = [
    re.compile(r'\b(stripe\s+[a-z_-]+|paypal\s+[a-z_-]+|aws\s+ce\b|gcloud\s+billing\b)', re.I),
]
EGRESS_BLOCKED_PATTERNS = [
    re.compile(r'\b(nc\s+-e|nc\s+-l|scp\s+|rsync\s+.*@)', re.I),
]
SECRET_PATTERNS = [
    re.compile(r'\b(cat|less|head|grep|tail|sed)\b.*(?:\s|^)(\.env|id_rsa|credentials|[\w.-]+\.(?:pem|key))(?:\s|$)', re.I),
]
DEPLOY_PATTERNS = [
    re.compile(r'\b(npm\s+publish|kubectl\s+apply|terraform\s+apply|vercel\b.*--prod)\b', re.I),
]
DISK_DESTROY_PATTERNS = [
    re.compile(r'\b(mkfs|dd\s+if=.*of=/dev/|>\s*/dev/sd[a-z])\b', re.I),
]

# Whitelist for loopback/localhost requests (e.g. testing local server)
LOOPBACK_RE = re.compile(r'\b(curl|wget)\b.*(https?://)?(localhost|127\.0\.0\.1|0\.0\.0\.0|::1)(:\d+)?', re.I)

def check_hard_floor(cmd: str, worktree_root: str = "") -> Optional[GuardResult]:
    """Non-overridable Layer 1 evaluation. Returns GuardResult if blocked, None if clean."""
    if not cmd:
        return None

    # Exempt package managers installing packages (e.g. pip install stripe, npm i stripe)
    is_pkg_install = bool(re.search(r'\b(pip|pip3|npm|yarn|pnpm|cargo|poetry|go\s+get|go\s+install)\b', cmd, re.I))

    if not is_pkg_install:
        for p in BILLING_PATTERNS:
            if p.search(cmd):
                return GuardResult(Decision.DENY, "FLOOR:billing", "Billing/payment command blocked")

    # Check secret reads, exempting example/template/test env configs
    is_safe_env = bool(re.search(r'\.env\.(example|sample|template|test|dist)\b', cmd, re.I))
    if not is_safe_env:
        for p in SECRET_PATTERNS:
            if p.search(cmd):
                return GuardResult(Decision.DENY, "FLOOR:secret-read", "Secret file read/exfiltration blocked")

    for p in DEPLOY_PATTERNS:
        if p.search(cmd):
            return GuardResult(Decision.DENY, "FLOOR:prod-deploy", "Production deploy blocked")
    for p in DISK_DESTROY_PATTERNS:
        if p.search(cmd):
            return GuardResult(Decision.DENY, "FLOOR:disk-destroy", "Destructive disk formatting/write blocked")

    # Check network egress (block raw sockets, allow localhost/loopback curl/wget)
    for p in EGRESS_BLOCKED_PATTERNS:
        if p.search(cmd):
            return GuardResult(Decision.DENY, "FLOOR:egress", "Unrestricted network egress blocked")

    # If curl/wget is used, allow loopback (localhost:PORT)
    if re.search(r'\b(curl|wget)\b', cmd, re.I):
        if not LOOPBACK_RE.search(cmd) and not is_pkg_install:
            return GuardResult(Decision.DENY, "FLOOR:egress", "Unrestricted external network egress blocked (use localhost)")

    return None


# ═══════════════════════════════════════════════════════════
# LAYER 2: CONFIGURABLE GUARDRAILS (R01-R15 equivalent)
# ═══════════════════════════════════════════════════════════

def _rule_no_sudo(tool_name: str, cmd: str, args: dict, ctx: GuardContext) -> Optional[GuardResult]:
    if re.search(r'\bsudo\b', cmd):
        return GuardResult(Decision.DENY, "R01:no-sudo", "Privilege escalation (sudo) is forbidden")
    return None

def _rule_no_chmod_777(tool_name: str, cmd: str, args: dict, ctx: GuardContext) -> Optional[GuardResult]:
    if re.search(r'\bchmod\s+(-R\s+)?777\b', cmd):
        return GuardResult(Decision.DENY, "R02:no-chmod-777", "Insecure permissions (chmod 777) forbidden")
    return None

def _rule_path_containment(tool_name: str, cmd: str, args: dict, ctx: GuardContext) -> Optional[GuardResult]:
    # Check target paths in write/read/edit file tools
    for key in ("path", "target_file", "file_path", "filename"):
        if key in args:
            path_val = str(args[key])
            if ".." in path_val:
                # If a worktree root is defined, verify path resolves within it
                if ctx.worktree_root:
                    try:
                        resolved = Path(ctx.worktree_root, path_val).resolve()
                        root_resolved = Path(ctx.worktree_root).resolve()
                        if not str(resolved).startswith(str(root_resolved)):
                            return GuardResult(Decision.DENY, "R03:path-escape", f"Path escapes workspace: {path_val}")
                    except Exception:
                        return GuardResult(Decision.DENY, "R03:path-escape", f"Invalid path: {path_val}")
    return None

def _rule_db_drop(tool_name: str, cmd: str, args: dict, ctx: GuardContext) -> Optional[GuardResult]:
    if re.search(r'\b(drop\s+table|drop\s+database|truncate\s+table)\b', cmd, re.I):
        # Allow DROP TABLE IF EXISTS in local test files or sqlite
        if "if exists" in cmd.lower() or "test" in cmd.lower():
            return None
        return GuardResult(Decision.DENY, "R04:db-drop", "Destructive database operations blocked")
    return None

SAFE_RM_PATTERNS = re.compile(r'\brm\s+-(r|rf|fr)\s+(build|dist|__pycache__|\.pytest_cache|\.mypy_cache|node_modules/\.cache|\.test_venv|\.cache|\*\.egg-info)\b', re.I)

def _rule_confirm_rm_rf(tool_name: str, cmd: str, args: dict, ctx: GuardContext) -> Optional[GuardResult]:
    if re.search(r'\brm\s+.*-(r|rf|fr)\b', cmd):
        if SAFE_RM_PATTERNS.search(cmd):
            return None  # Safe build/cache cleanup
        return GuardResult(Decision.ASK, "R05:confirm-rm-rf", f"Destructive command requires confirmation: {cmd[:80]}")
    return None

def _rule_no_force_push(tool_name: str, cmd: str, args: dict, ctx: GuardContext) -> Optional[GuardResult]:
    if re.search(r'git\s+push\b.*(--force|-f\b)', cmd):
        return GuardResult(Decision.DENY, "R06:no-force-push", "git push --force is strictly forbidden")
    return None

def _rule_no_git_hard_reset(tool_name: str, cmd: str, args: dict, ctx: GuardContext) -> Optional[GuardResult]:
    if re.search(r'git\s+reset\b.*--hard', cmd):
        return GuardResult(Decision.ASK, "R07:git-hard-reset", "git reset --hard requires explicit confirmation")
    return None

def _rule_read_only_role(tool_name: str, cmd: str, args: dict, ctx: GuardContext) -> Optional[GuardResult]:
    if ctx.active_role in ("reviewer", "readonly", "auditor"):
        mutating_tools = ("write_file", "edit_file", "apply_patch", "delete_file")
        if tool_name in mutating_tools:
            return GuardResult(Decision.DENY, "R08:read-only-role", f"Role '{ctx.active_role}' cannot modify files")
    return None

def _rule_no_git_bypass(tool_name: str, cmd: str, args: dict, ctx: GuardContext) -> Optional[GuardResult]:
    if re.search(r'git\s+commit\b.*--no-verify', cmd):
        return GuardResult(Decision.DENY, "R10:no-git-bypass", "Bypassing git hooks (--no-verify) is forbidden")
    return None


DEFAULT_GUARDRAILS = [
    _rule_no_sudo,
    _rule_no_chmod_777,
    _rule_path_containment,
    _rule_db_drop,
    _rule_confirm_rm_rf,
    _rule_no_force_push,
    _rule_no_git_hard_reset,
    _rule_read_only_role,
    _rule_no_git_bypass,
]


class SafetyGate:
    """
    Unified Two-Tier Safety Gate implementing the ToolGuard protocol.
    """
    def __init__(self, custom_rules: Optional[List[Callable]] = None):
        self.rules = list(DEFAULT_GUARDRAILS)
        if custom_rules:
            self.rules.extend(custom_rules)

    def add_rule(self, rule_fn: Callable) -> None:
        self.rules.append(rule_fn)

    def evaluate(self, tool_name: str, args: Dict[str, Any], context: Optional[GuardContext] = None) -> GuardDecision:
        ctx = context or GuardContext()
        cmd = str(args.get("command", args.get("cmd", "")))

        # Layer 1: Runtime Hard Floor (unconditional)
        floor_result = check_hard_floor(cmd, ctx.worktree_root)
        if floor_result:
            return floor_result.to_guard_decision()

        # Layer 2: Configurable Guardrails (evaluated in order)
        for rule in self.rules:
            res = rule(tool_name, cmd, args, ctx)
            if res is not None:
                return res.to_guard_decision()

        return GuardResult(Decision.ALLOW).to_guard_decision()


# Global helper instance
_global_gate = SafetyGate()

def evaluate_tool_call(tool_name: str, args: Dict[str, Any], context: Optional[GuardContext] = None) -> GuardDecision:
    """Entry point for tool safety verification."""
    return _global_gate.evaluate(tool_name, args, context)
