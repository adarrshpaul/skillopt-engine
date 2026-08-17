"""
Structured tool dispatch pipeline with pre/post waterfalls.
Inspired by DeepSeek Harness tool execution pipeline (tools/pre-execute -> execute -> finalizeContent -> tools/result).
"""
import re
import json
import traceback
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Any, Dict, Tuple
from core.safety_gate import evaluate_tool_call, Decision
from core.session_ledger import SessionEvent, JSONLSessionLedger
from contracts import GuardContext

@dataclass
class ToolCall:
    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    call_id: str = ""

@dataclass
class ToolResult:
    content: str
    is_error: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

# Middleware signatures
PreMiddleware = Callable[[ToolCall, Dict[str, Any]], Optional[ToolResult]]
PostMiddleware = Callable[[ToolCall, ToolResult, Dict[str, Any]], ToolResult]


class ToolPipeline:
    """Waterfall-style tool execution pipeline with pre/post execution middleware."""

    def __init__(self, ledger: Optional[Any] = None):
        self._tools: Dict[str, Callable] = {}
        self._pre_hooks: List[PreMiddleware] = []
        self._post_hooks: List[PostMiddleware] = []
        self._ledger = ledger

        # Register default pre-hook: Safety Gate
        self.add_pre_hook(safety_gate_hook)
        # Register default post-hook: Compactor
        self.add_post_hook(compaction_hook)

    def register_tool(self, name: str, handler: Callable) -> None:
        self._tools[name] = handler

    def add_pre_hook(self, hook: PreMiddleware) -> None:
        self._pre_hooks.append(hook)

    def add_post_hook(self, hook: PostMiddleware) -> None:
        self._post_hooks.append(hook)

    def dispatch(self, call: ToolCall, context: Optional[Dict[str, Any]] = None) -> ToolResult:
        ctx = context or {}

        # 1. Log tool/call event
        if self._ledger:
            self._ledger.append(SessionEvent(
                event_type="tool/call",
                payload={"tool": call.name, "args": call.args, "call_id": call.call_id}
            ))

        # 2. Pre-execution waterfall (e.g. Safety Gate)
        for hook in self._pre_hooks:
            denial = hook(call, ctx)
            if denial is not None:
                if self._ledger:
                    self._ledger.append(SessionEvent(
                        event_type="tool/result",
                        payload={"tool": call.name, "output": denial.content, "is_error": True}
                    ))
                return denial

        # 3. Execution
        handler = self._tools.get(call.name)
        if not handler:
            result = ToolResult(content=f"Error: Unknown tool '{call.name}'", is_error=True)
        else:
            try:
                raw_out = handler(**call.args)
                result = ToolResult(content=str(raw_out))
            except Exception as e:
                result = ToolResult(
                    content=f"Tool Execution Error ({call.name}): {str(e)}\n{traceback.format_exc()}",
                    is_error=True
                )

        # 4. Post-execution waterfall (e.g. Compaction / Truncation / Formatting)
        for hook in self._post_hooks:
            result = hook(call, result, ctx)

        # 5. Log tool/result event
        if self._ledger:
            self._ledger.append(SessionEvent(
                event_type="tool/result",
                payload={"tool": call.name, "output": result.content[:1000], "is_error": result.is_error}
            ))

        return result


def safety_gate_hook(call: ToolCall, context: Dict[str, Any]) -> Optional[ToolResult]:
    """Pre-hook: 2-tier safety evaluation."""
    worktree = context.get("worktree_root", "")
    role = context.get("active_role", "")
    guard_ctx = GuardContext(worktree_root=worktree, active_role=role)
    guard = evaluate_tool_call(call.name, call.args, guard_ctx)

    if guard.decision == "deny":
        return ToolResult(
            content=f"BLOCKED [{guard.rule_id}]: {guard.reason}",
            is_error=True,
            metadata={"rule_id": guard.rule_id, "decision": "deny"}
        )
    return None


def compaction_hook(call: ToolCall, result: ToolResult, context: Dict[str, Any]) -> ToolResult:
    """Post-hook: Compress or truncate tool outputs exceeding 3000 chars."""
    if len(result.content) > 3000:
        try:
            from claw_compactor.fusion.pipeline import FusionPipeline
            compressed, _ = FusionPipeline().run(result.content)
            result.content = compressed
        except Exception:
            # Fallback: smart truncation preserving head and tail
            head = result.content[:1500]
            tail = result.content[-1500:]
            result.content = f"{head}\n\n... [Output truncated ({len(result.content)} bytes total)] ...\n\n{tail}"
    return result


def parse_tool_calls_from_text(text: str) -> Tuple[List[ToolCall], List[str]]:
    """
    Robust multi-grammar tool parser. Supports:
    1. <execute>tool_name(args...)</execute> grammar (Ornith/Qwen format)
    2. JSON object tool calls: {"name": "...", "arguments": {...}}
    3. Python function call syntax: tool_name(arg="val")
    """
    calls: List[ToolCall] = []
    parse_errors: List[str] = []

    # 1. <execute>...</execute> syntax
    exec_blocks = re.findall(r'<execute>(.*?)</execute>', text, re.DOTALL)
    for block in exec_blocks:
        block = block.strip()
        # Parse tool name and args
        m = re.match(r'^([a-zA-Z0-9_]+)\s*\((.*)\)$', block, re.DOTALL)
        if m:
            tool_name = m.group(1)
            raw_args = m.group(2).strip()
            args = _parse_args_string(tool_name, raw_args)
            calls.append(ToolCall(name=tool_name, args=args))
        else:
            # Check if JSON was provided inside execute tags
            try:
                dec = json.JSONDecoder()
                obj, _ = dec.raw_decode(block)
                if isinstance(obj, dict) and "name" in obj:
                    args = obj.get("arguments", obj.get("args", {}))
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            args = {"raw": args}
                    calls.append(ToolCall(name=obj["name"], args=args))
                    continue
            except Exception:
                pass
            parse_errors.append(f"Invalid function call syntax inside <execute>: `{block[:100]}...` - Expected format: <execute>tool_name(arg1, arg2)</execute>")

    if calls:
        return calls, parse_errors

    # 2. JSON tool block syntax: {"name": "...", "arguments": {...}}
    json_matches = re.finditer(r'\{[\s\S]*?"name"[\s\S]*?\}', text)
    for match in json_matches:
        try:
            # Try raw decode
            dec = json.JSONDecoder()
            obj, _ = dec.raw_decode(text[match.start():])
            if isinstance(obj, dict) and "name" in obj:
                args = obj.get("arguments", obj.get("args", {}))
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception as e:
                        parse_errors.append(f"JSON parsing error in arguments for tool '{obj['name']}': {str(e)}\nRaw string: {args}")
                        args = {"raw": args}
                calls.append(ToolCall(name=obj["name"], args=args))
        except Exception as e:
            parse_errors.append(f"Malformed JSON block detected: {str(e)}\nText snippet: {text[match.start():match.start()+100]}...")
            continue

    return calls, parse_errors


def _parse_args_string(tool_name: str, args_str: str) -> Dict[str, Any]:
    """Helper to parse Python-like arguments string into a dict using AST parsing with regex fallback."""
    if not args_str:
        return {}

    # Primary Strategy: Deterministic Python AST parsing
    try:
        import ast
        tree = ast.parse(f"_tool({args_str})")
        if isinstance(tree, ast.Module) and tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Call):
            call_node = tree.body[0].value
            pos_args = [ast.literal_eval(a) for a in call_node.args]
            kw_args = {kw.arg: ast.literal_eval(kw.value) for kw in call_node.keywords}
            
            result: Dict[str, Any] = dict(kw_args)
            if tool_name == "write_file":
                if len(pos_args) >= 1 and "path" not in result:
                    result["path"] = pos_args[0]
                if len(pos_args) >= 2 and "content" not in result:
                    result["content"] = pos_args[1]
            elif tool_name == "edit_file":
                if len(pos_args) >= 1 and "path" not in result:
                    result["path"] = pos_args[0]
                if len(pos_args) >= 2 and "old_text" not in result:
                    result["old_text"] = pos_args[1]
                if len(pos_args) >= 3 and "new_text" not in result:
                    result["new_text"] = pos_args[2]
            elif tool_name in ("run_command", "bash", "execute_bash", "exec"):
                if len(pos_args) >= 1 and "command" not in result:
                    result["command"] = pos_args[0]
            elif tool_name in ("read_file", "list_dir", "document_symbols"):
                if len(pos_args) >= 1 and "path" not in result:
                    result["path"] = pos_args[0]
            elif tool_name in ("find_definition", "find_references", "hover"):
                if len(pos_args) >= 1 and "symbol" not in result:
                    result["symbol"] = pos_args[0]
                if len(pos_args) >= 2 and "file_path" not in result:
                    result["file_path"] = pos_args[1]
            elif tool_name in ("ask_human", "ask_user"):
                if len(pos_args) >= 1 and "question" not in result:
                    result["question"] = pos_args[0]
            elif tool_name in ("delegate_task", "delegate"):
                if len(pos_args) >= 1 and "role" not in result:
                    result["role"] = pos_args[0]
                if len(pos_args) >= 2 and "task" not in result:
                    result["task"] = pos_args[1]
            else:
                for idx, pa in enumerate(pos_args):
                    result[f"arg_{idx}"] = pa
            
            if result:
                return result
    except Exception:
        pass

    # Fallback for multi-line write_file/edit_file with literal unescaped newlines in quotes
    if tool_name in ("write_file", "edit_file") and (args_str.startswith('"') or args_str.startswith("'")):
        try:
            q = args_str[0]
            end_q = args_str.find(q, 1)
            if end_q != -1:
                path = args_str[1:end_q]
                rest = args_str[end_q+1:].strip()
                if rest.startswith(","):
                    content_raw = rest[1:].strip()
                    if content_raw.startswith('"""') and content_raw.endswith('"""') and len(content_raw) >= 6:
                        content = content_raw[3:-3]
                    elif content_raw.startswith("'''") and content_raw.endswith("'''") and len(content_raw) >= 6:
                        content = content_raw[3:-3]
                    elif (content_raw.startswith('"') and content_raw.endswith('"')) or (content_raw.startswith("'") and content_raw.endswith("'")):
                        content = content_raw[1:-1]
                    else:
                        content = content_raw
                    # Unescape standard escape sequences if encoded
                    content = content.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace("\\'", "'")
                    return {"path": path, "content": content}
        except Exception:
            pass

    # Simple single string argument (e.g. run_command("ls -la") or run_command('ls -la'))
    if (args_str.startswith('"') and args_str.endswith('"')) or (args_str.startswith("'") and args_str.endswith("'")):
        clean_str = args_str[1:-1].replace('\\"', '"').replace("\\'", "'")
        if tool_name in ("run_command", "bash", "execute_bash", "exec"):
            return {"command": clean_str}
        if tool_name in ("read_file", "list_dir", "document_symbols"):
            return {"path": clean_str}
        if tool_name in ("find_definition", "find_references", "hover"):
            return {"symbol": clean_str}
        if tool_name in ("ask_human", "ask_user"):
            return {"question": clean_str}

    # Fallback Strategy: Named args key=value parsing via regex
    args: Dict[str, Any] = {}
    pattern = re.finditer(r'([a-zA-Z0-9_]+)\s*=\s*(?:"""([\s\S]*?)"""|\'\'\'([\s\S]*?)\'\'\'|"([^"\\]*(?:\\.[^"\\]*)*)"|\'([^\'\\]*(?:\\.[^\'\\]*)*)\'|([^,]+))', args_str)
    for match in pattern:
        k = match.group(1)
        val = match.group(2) or match.group(3) or match.group(4) or match.group(5) or match.group(6)
        if val is not None:
            args[k] = val.strip().replace('\\n', '\n').replace('\\"', '"').replace("\\'", "'")

    if not args and args_str:
        if tool_name in ("run_command", "bash", "execute_bash", "exec"):
            return {"command": args_str.strip('"\'')}
        if tool_name in ("find_definition", "find_references", "hover"):
            return {"symbol": args_str.strip('"\'')}
        if tool_name in ("ask_human", "ask_user"):
            return {"question": args_str.strip('"\'')}
        return {"raw_arg": args_str.strip('"\'')}

    return args
