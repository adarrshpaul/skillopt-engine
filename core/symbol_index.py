"""
AST-based Symbol Index and Static Repo Map Generator.
Inspired by Aider's tree-sitter repo map and Serena's code intelligence layer.
Maintains an incremental cache (.repomap_cache.json) based on file hashes and mtimes,
constructs def-to-ref symbol graphs, and builds token-budgeted architectural outlines.
"""
import ast
import os
import json
import hashlib
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Set, Optional, Any, Tuple

@dataclass
class SymbolDef:
    name: str
    kind: str  # "class", "function", "method", "async_function"
    file_path: str
    line_number: int
    end_line: int
    docstring: str = ""
    args: List[str] = field(default_factory=list)
    parent: Optional[str] = None

@dataclass
class SymbolRef:
    name: str
    file_path: str
    line_number: int


class ASTSymbolVisitor(ast.NodeVisitor):
    """Extracts all definitions, calls, and imports from Python AST."""
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.definitions: List[SymbolDef] = []
        self.references: List[SymbolRef] = []
        self.imports: List[str] = []
        self._scope_stack: List[str] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        doc = ast.get_docstring(node) or ""
        sym = SymbolDef(
            name=node.name,
            kind="class",
            file_path=self.file_path,
            line_number=node.lineno,
            end_line=getattr(node, 'end_lineno', node.lineno),
            docstring=doc.split("\n")[0] if doc else "",
            args=[b.id for b in node.bases if isinstance(b, ast.Name)],
            parent=self._scope_stack[-1] if self._scope_stack else None
        )
        self.definitions.append(sym)
        self._scope_stack.append(node.name)
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._record_func(node, kind="method" if self._scope_stack else "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._record_func(node, kind="async_method" if self._scope_stack else "async_function")

    def _record_func(self, node: Any, kind: str):
        doc = ast.get_docstring(node) or ""
        args = [arg.arg for arg in node.args.args if arg.arg != "self"]
        sym = SymbolDef(
            name=node.name,
            kind=kind,
            file_path=self.file_path,
            line_number=node.lineno,
            end_line=getattr(node, 'end_lineno', node.lineno),
            docstring=doc.split("\n")[0] if doc else "",
            args=args,
            parent=self._scope_stack[-1] if self._scope_stack else None
        )
        self.definitions.append(sym)
        self._scope_stack.append(node.name)
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            self.references.append(SymbolRef(name=node.func.id, file_path=self.file_path, line_number=node.lineno))
        elif isinstance(node.func, ast.Attribute):
            self.references.append(SymbolRef(name=node.func.attr, file_path=self.file_path, line_number=node.lineno))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        mod = node.module or ""
        for alias in node.names:
            self.imports.append(f"{mod}.{alias.name}")
            self.references.append(SymbolRef(name=alias.name, file_path=self.file_path, line_number=node.lineno))
        self.generic_visit(node)


class SymbolIndex:
    """
    Incremental Code Symbol Index & PageRank-based Repository Map.
    """
    def __init__(self, workspace_root: str = ".", cache_file: str = ".repomap_cache.json"):
        self.workspace_root = os.path.abspath(workspace_root)
        self.cache_file = os.path.join(self.workspace_root, cache_file)
        self._cache: Dict[str, Any] = self._load_cache()
        self.definitions: List[SymbolDef] = []
        self.references: List[SymbolRef] = []
        self._indexed_files: Set[str] = set()

    def _load_cache(self) -> Dict[str, Any]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self) -> None:
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)
        except Exception:
            pass

    def _compute_hash(self, file_path: str) -> str:
        try:
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception:
            return ""

    def scan_workspace(self, max_files: int = 200) -> None:
        """Incrementally scans and parses all Python files in the workspace."""
        self.definitions = []
        self.references = []
        self._indexed_files = set()
        
        ignored_dirs = {
            ".git", ".test_venv", "tb-env", "ml-env", "__pycache__",
            "node_modules", ".venv", "env", "build", "dist"
        }

        count = 0
        for root, dirs, files in os.walk(self.workspace_root):
            dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.workspace_root)
                    self._parse_file(full_path, rel_path)
                    count += 1
                    if count >= max_files:
                        break
            if count >= max_files:
                break

        self._save_cache()

    def _parse_file(self, full_path: str, rel_path: str) -> None:
        if not os.path.exists(full_path):
            return

        mtime = os.path.getmtime(full_path)
        file_hash = self._compute_hash(full_path)
        cached = self._cache.get(rel_path)

        if cached and cached.get("hash") == file_hash and cached.get("mtime") == mtime:
            # Load from incremental cache
            for d in cached.get("definitions", []):
                self.definitions.append(SymbolDef(**d))
            for r in cached.get("references", []):
                self.references.append(SymbolRef(**r))
            self._indexed_files.add(rel_path)
            return

        # Parse fresh AST
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
            tree = ast.parse(source, filename=rel_path)
            visitor = ASTSymbolVisitor(rel_path)
            visitor.visit(tree)

            self.definitions.extend(visitor.definitions)
            self.references.extend(visitor.references)
            self._indexed_files.add(rel_path)

            # Update cache entry
            self._cache[rel_path] = {
                "hash": file_hash,
                "mtime": mtime,
                "definitions": [asdict(d) for d in visitor.definitions],
                "references": [asdict(r) for r in visitor.references]
            }
        except Exception:
            pass

    def get_condensed_repo_map(self, max_tokens: int = 1500) -> str:
        """
        Generates a token-budgeted, hierarchical outline of the codebase symbols.
        Ranks symbols based on reference frequency across files.
        """
        if not self.definitions:
            self.scan_workspace()

        if not self.definitions:
            return ""

        # Compute reference frequency
        ref_counts: Dict[str, int] = {}
        for r in self.references:
            ref_counts[r.name] = ref_counts.get(r.name, 0) + 1

        # Group definitions by file
        files_map: Dict[str, List[SymbolDef]] = {}
        for d in self.definitions:
            files_map.setdefault(d.file_path, []).append(d)

        # Score each file by total reference popularity
        file_scores: List[Tuple[str, int]] = []
        for file_path, syms in files_map.items():
            score = sum(ref_counts.get(s.name, 1) for s in syms)
            file_scores.append((file_path, score))

        file_scores.sort(key=lambda x: x[1], reverse=True)

        lines: List[str] = ["# 🗺️ Workspace Symbol Map (AST Def-Ref Graph)"]
        current_chars = 0
        char_budget = max_tokens * 4

        for file_path, _ in file_scores:
            syms = files_map[file_path]
            file_header = f"\n📄 {file_path}:"
            lines.append(file_header)
            current_chars += len(file_header)

            for sym in syms:
                args_str = f"({', '.join(sym.args[:4])})" if sym.args else "()"
                indent = "    " if sym.parent else "  "
                doc_snippet = f" — {sym.docstring}" if sym.docstring else ""
                entry = f"{indent}• {sym.kind} {sym.name}{args_str} [L{sym.line_number}]{doc_snippet}"
                
                if current_chars + len(entry) > char_budget:
                    lines.append("  ... [Remaining symbols truncated for token budget]")
                    return "\n".join(lines)

                lines.append(entry)
                current_chars += len(entry)

        return "\n".join(lines)

    def find_definition(self, symbol_name: str, target_file: Optional[str] = None) -> List[Dict[str, Any]]:
        """Finds all definition locations for a given symbol."""
        if not self.definitions:
            self.scan_workspace()

        results = []
        for d in self.definitions:
            if d.name == symbol_name:
                if target_file and d.file_path != target_file:
                    continue
                results.append(asdict(d))
        return results

    def find_references(self, symbol_name: str, target_file: Optional[str] = None) -> List[Dict[str, Any]]:
        """Finds all call/import reference locations for a given symbol."""
        if not self.references:
            self.scan_workspace()

        results = []
        for r in self.references:
            if r.name == symbol_name:
                if target_file and r.file_path != target_file:
                    continue
                results.append(asdict(r))
        return results

    def document_symbols(self, file_path: str) -> List[Dict[str, Any]]:
        """Lists all symbols defined in a specific document."""
        if not self.definitions:
            self.scan_workspace()

        clean_path = os.path.relpath(file_path, self.workspace_root) if os.path.isabs(file_path) else file_path
        return [asdict(d) for d in self.definitions if d.file_path == clean_path or d.file_path == file_path]

    def hover(self, symbol_name: str, file_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Provides docstring, signature, and definition metadata for hover inspection."""
        defs = self.find_definition(symbol_name, file_path)
        if defs:
            d = defs[0]
            args_str = f"({', '.join(d.get('args', []))})"
            return {
                "symbol": symbol_name,
                "kind": d.get("kind"),
                "signature": f"{d.get('name')}{args_str}",
                "file_path": d.get("file_path"),
                "line_number": d.get("line_number"),
                "docstring": d.get("docstring") or "No docstring provided."
            }
        return None
