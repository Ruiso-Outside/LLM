"""Servidor MCP falso (stdio) para os testes: ferramentas echo (leitura), set_value (altera) e snapshot (imagem)."""
import base64
import json
import sys

STATE = {"value": None}
TOOLS = [
    {"name": "echo", "description": "Devolve o texto", "annotations": {"readOnlyHint": True},
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "set_value", "description": "Guarda um valor",
     "inputSchema": {"type": "object", "properties": {"value": {"type": "string"}}}},
    {"name": "snapshot", "description": "Devolve uma imagem", "annotations": {"readOnlyHint": True},
     "inputSchema": {"type": "object", "properties": {}}},
]
PNG = base64.b64encode(bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                                     "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")).decode()


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    msg = json.loads(line)
    if "method" not in msg:  # resposta a um pedido nosso (ping)
        continue
    mid, method, params = msg.get("id"), msg["method"], msg.get("params") or {}
    if mid is None:
        if method == "notifications/initialized":
            send({"jsonrpc": "2.0", "id": "srv-ping", "method": "ping"})  # o cliente precisa responder
        continue
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": params.get("protocolVersion"), "capabilities": {"tools": {}},
                                                      "serverInfo": {"name": "fake", "version": "1"},
                                                      "instructions": "Servidor de teste."}})
    elif method == "tools/list":
        if not params.get("cursor"):
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS[:2], "nextCursor": "p2"}})
        else:
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS[2:]}})
    elif method == "tools/call":
        name, args = params["name"], params.get("arguments") or {}
        if name == "echo":
            res = {"content": [{"type": "text", "text": "eco: " + args.get("text", "")}]}
        elif name == "set_value":
            STATE["value"] = args.get("value")
            res = {"content": [{"type": "text", "text": f"valor = {STATE['value']}"}]}
        elif name == "snapshot":
            res = {"content": [{"type": "image", "data": PNG, "mimeType": "image/png"}]}
        else:
            res = {"content": [{"type": "text", "text": "ferramenta desconhecida"}], "isError": True}
        send({"jsonrpc": "2.0", "id": mid, "result": res})
    else:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "Method not found"}})
