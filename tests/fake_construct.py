"""Arasaka Construct falso para os testes: `fake_construct.py [projeto] --mcp`, MCP por stdio.

Imita as ferramentas do editor que a Mikoshi usa (project_info, write_image, create_sprite, read_file) e grava de
verdade na pasta do projeto, como o demonic-editor.
"""
import base64
import json
import sys
from pathlib import Path

args = [a for a in sys.argv[1:] if a != "--mcp"]
PROJECT = Path(args[0]) if args else None
TOOLS = [
    {"name": "project_info", "description": "Projeto aberto", "annotations": {"readOnlyHint": True},
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "read_file", "description": "Le um arquivo de texto", "annotations": {"readOnlyHint": True},
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_image", "description": "Grava um PNG",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "data": {"type": "string"}}, "required": ["path", "data"]}},
    {"name": "create_sprite", "description": "Cria um sprite animado",
     "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "animations": {"type": "array"}}, "required": ["name", "animations"]}},
]


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def inside(rel):
    if PROJECT is None:
        raise ValueError("nenhum projeto aberto")
    if rel.startswith("/") or ".." in Path(rel).parts:
        raise ValueError("caminho fora do projeto: " + rel)
    return PROJECT / rel


def run(name, a):
    if name == "project_info":
        return f"Projeto: {PROJECT}"
    if name == "read_file":
        return inside(a["path"]).read_text("utf-8")
    if name == "write_image":
        data = base64.b64decode(a["data"])
        if not data.startswith(b"\x89PNG"):
            raise ValueError("os dados nao sao um PNG")
        p = inside(a["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return f"Criado: {a['path']}"
    if name == "create_sprite":
        p = inside(f"sprites/{a['name']}.sprite.luau")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("return " + json.dumps({"kind": "sprite", "animations": a["animations"]}), "utf-8")
        return f"Criado: sprites/{a['name']}.sprite.luau"
    raise ValueError("ferramenta desconhecida")


for line in sys.stdin:
    msg = json.loads(line)
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        continue
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": params.get("protocolVersion"), "capabilities": {"tools": {}},
                                                      "serverInfo": {"name": "demonic-engine", "version": "9.9.9"}}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        try:
            send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": run(params["name"], params.get("arguments") or {})}]}})
        except (ValueError, OSError, KeyError) as e:
            send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": str(e)}], "isError": True}})
    else:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "nao suportado"}})
