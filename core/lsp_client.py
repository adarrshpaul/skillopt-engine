"""
Language Server Protocol (LSP) & Code Intelligence Client.
Inspired by Serena/multilspy and Aider's code navigation.
Exposes synchronous, agentic ReAct tools for semantic symbol exploration:
1. find_definition: Locates exact class/function definitions across files.
2. find_references: Locates all callers and instantiations.
3. document_symbols: Extracts the hierarchical outline of a file.
4. hover: Retrieves type signatures and docstrings for a symbol.
"""
import os
import json
from typing import Dict, Any, Optional
from core.symbol_index import SymbolIndex

# Global singleton symbol index
_symbol_index: Optional[SymbolIndex] = None

def get_symbol_index(workspace_root: str = ".") -> SymbolIndex:
    global _symbol_index
    if _symbol_index is None:
        _symbol_index = SymbolIndex(workspace_root=workspace_root)
    return _symbol_index


def handle_find_definition(args: Dict[str, Any], context: Dict[str, Any]) -> str:
    """Tool handler for find_definition(symbol, file_path=None)."""
    symbol = str(args.get("symbol", args.get("name", args.get("raw_arg", "")))).strip()
    if not symbol:
        return "ERROR: find_definition requires 'symbol' parameter."
    
    file_path = args.get("file_path", args.get("path"))
    idx = get_symbol_index(context.get("workspace_root", "."))
    results = idx.find_definition(symbol, target_file=file_path)
    
    if not results:
        return f"No definition found for symbol '{symbol}'."
    
    lines = [f"Found {len(results)} definition(s) for '{symbol}':"]
    for r in results:
        args_str = f"({', '.join(r.get('args', []))})"
        lines.append(f"  • {r.get('file_path')}:{r.get('line_number')} [{r.get('kind')}] {r.get('name')}{args_str}")
        if r.get("docstring"):
            lines.append(f"    Docstring: {r.get('docstring')}")
    return "\n".join(lines)


def handle_find_references(args: Dict[str, Any], context: Dict[str, Any]) -> str:
    """Tool handler for find_references(symbol, file_path=None)."""
    symbol = str(args.get("symbol", args.get("name", args.get("raw_arg", "")))).strip()
    if not symbol:
        return "ERROR: find_references requires 'symbol' parameter."
    
    file_path = args.get("file_path", args.get("path"))
    idx = get_symbol_index(context.get("workspace_root", "."))
    results = idx.find_references(symbol, target_file=file_path)
    
    if not results:
        return f"No references found for symbol '{symbol}'."
    
    lines = [f"Found {len(results)} reference(s) for '{symbol}':"]
    for r in results[:30]:  # Limit output to 30 to prevent context bloat
        lines.append(f"  • {r.get('file_path')}:{r.get('line_number')} (call/import site)")
    if len(results) > 30:
        lines.append(f"  ... [{len(results) - 30} additional references truncated]")
    return "\n".join(lines)


def handle_document_symbols(args: Dict[str, Any], context: Dict[str, Any]) -> str:
    """Tool handler for document_symbols(path)."""
    file_path = str(args.get("path", args.get("file_path", args.get("raw_arg", "")))).strip()
    if not file_path:
        return "ERROR: document_symbols requires 'path' parameter."
    
    idx = get_symbol_index(context.get("workspace_root", "."))
    symbols = idx.document_symbols(file_path)
    
    if not symbols:
        return f"No symbols found in '{file_path}' (or file is not a valid Python module)."
    
    lines = [f"Document symbols in {file_path} ({len(symbols)} total):"]
    for s in symbols:
        indent = "    " if s.get("parent") else "  "
        args_str = f"({', '.join(s.get('args', []))})"
        lines.append(f"{indent}• [{s.get('kind')}] {s.get('name')}{args_str} at line {s.get('line_number')}")
    return "\n".join(lines)


def handle_hover(args: Dict[str, Any], context: Dict[str, Any]) -> str:
    """Tool handler for hover(symbol, file_path=None)."""
    symbol = str(args.get("symbol", args.get("name", args.get("raw_arg", "")))).strip()
    if not symbol:
        return "ERROR: hover requires 'symbol' parameter."
    
    file_path = args.get("file_path", args.get("path"))
    idx = get_symbol_index(context.get("workspace_root", "."))
    info = idx.hover(symbol, file_path)
    
    if not info:
        return f"No hover/type information found for '{symbol}'."
    
    return (
        f"Symbol: {info.get('symbol')} ({info.get('kind')})\n"
        f"Location: {info.get('file_path')}:{info.get('line_number')}\n"
        f"Signature: {info.get('signature')}\n"
        f"Documentation: {info.get('docstring')}"
    )
