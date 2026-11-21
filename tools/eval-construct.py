#!/usr/bin/env python3
"""Mede o quanto o Codex da Mikoshi sabe usar o Arasaka Construct, com um modelo local de verdade.

Sobe a Mikoshi isolada (pasta de dados temporaria; os modelos e o motor por atalho), conectada ao editor do Construct,
e para cada tarefa: cria um projeto novo do modelo "cena", pede a tarefa ao Codex (so ferramentas MCP, confirmacoes
automaticas) e confere o resultado sem depender da IA: o codigo passa no check_code, o jogo roda sem erro e a mudanca
pedida existe na cena.

  python3 tools/eval-construct.py --home /media/.../  --model Qwen3.5-9B-...gguf \
      --editor ~/piphin/ArasakaConstruct/build/linux-release/bin/demonic-editor [--tasks slime,vida,moedas] [--out res.json]
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

TASKS = {
    "slime": "Na cena main do projeto aberto no Arasaka Construct, crie um inimigo chamado Slime em x=250, y=146 que anda "
             "sozinho de um lado para o outro (patrulha de uns 60 pixels). Escreva o comportamento num script "
             "scripts/slime.luau preso ao Slime.",
    "vida": "No projeto aberto no Arasaka Construct: o jogador comeca com 3 de vida e perde 1 quando encosta no Guarda, "
            "voltando ao ponto de partida. Mostre a vida num texto na interface da cena main (ex.: 'Vida: 3').",
    "moedas": "Na cena main do projeto aberto no Arasaka Construct, adicione 4 moedas novas dentro da pasta Moedas, usando "
              "o original prefabs/moeda.prefab.luau, enfileiradas em y=96 com x de 112 a 160.",
    "tiro": "No projeto aberto no Arasaka Construct, faca o jogador atirar quando apertar a tecla X: uma bolinha amarela "
            "que sai na direcao em que ele esta olhando, anda reto e some ao bater numa parede ou depois de 2 segundos.",
    "fase2": "No projeto aberto no Arasaka Construct, crie uma segunda cena chamada fase2 (pode ser simples, com chao e o "
             "jogador) e ponha no fim da cena main um objeto Bandeira: quando o jogador encostar nela, o jogo vai para a fase2.",
}


class Construct:
    """Cliente MCP minimo do editor, para conferir o resultado (independente da Mikoshi)."""

    def __init__(self, editor, project):
        self.p = subprocess.Popen([editor, str(project), "--mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True)
        self.n = 0
        self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "eval", "version": "1"}})

    def rpc(self, method, params=None):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}) + "\n")
        self.p.stdin.flush()
        while True:
            m = json.loads(self.p.stdout.readline())
            if m.get("id") == self.n:
                return m

    def tool(self, name, **a):
        r = self.rpc("tools/call", {"name": name, "arguments": a}).get("result", {})
        return r.get("isError", False), "".join(c.get("text", "") for c in r.get("content", []))

    def close(self):
        self.p.kill()


def scene_nodes(c):
    bad, out = c.tool("read_scene", scene="main")
    if bad or "JSON:" not in out:
        return []
    return json.loads(out.split("JSON:", 1)[1]).get("nodes", [])


def check(task, project, editor, demonic):
    c = Construct(editor, project)
    try:
        nodes = scene_nodes(c)
        bad, code = c.tool("check_code")
        code_ok = not bad and "Sem erros" in code
    finally:
        c.close()
    run = subprocess.run([demonic, str(project), "--hidden", "--frames", "120"], capture_output=True, text=True, timeout=120)
    errs = sorted(set(l for l in (run.stdout + run.stderr).splitlines() if re.search(r"\b(ERRO|erro|error)\b", l)))
    game_ok = run.returncode == 0 and not errs
    by_id = {n.get("id"): n for n in nodes}
    goal, why = False, ""
    if task == "slime":
        slime = next((n for n in nodes if str(n.get("name", "")).lower() == "slime"), None)
        script = slime and next((n for n in nodes if n.get("kind") == "script" and n.get("parent") == slime.get("id")), None)
        f = project / "scripts" / "slime.luau"
        goal = bool(slime and script and f.exists() and "update" in f.read_text("utf-8", "replace"))
        why = f"slime={bool(slime)} script_preso={bool(script)} arquivo={f.exists()}"
    elif task == "vida":
        ui_text = [n for n in nodes if n.get("kind") == "text" and (n.get("parent") == "ui" or by_id.get(n.get("parent"), {}).get("parent") == "ui")]
        src = " ".join(p.read_text("utf-8", "replace").lower() for p in (project / "scripts").glob("*.luau"))
        goal = bool(ui_text) and "vida" in src and ("guarda" in src or "overlap" in src)
        why = f"texto_na_interface={len(ui_text)} vida_no_script={'vida' in src}"
    elif task == "tiro":
        src = (project / "scripts" / "jogador.luau").read_text("utf-8", "replace") if (project / "scripts" / "jogador.luau").exists() else ""
        allsrc = src + " ".join(p.read_text("utf-8", "replace") for p in (project / "scripts").glob("*.luau"))
        # a tecla X ligada a uma acao (bind) ou usada direto: input.pressed("x") tambem vale (nome de tecla, sem diferenciar maiusculas)
        key = bool(re.search(r'bind\([^)]*["\']X["\']', allsrc, re.I) or re.search(r'input\.(pressed|down)\(\s*["\']x["\']', allsrc, re.I))
        shot = "spawn" in allsrc or "table.insert" in allsrc
        goal = key and shot
        why = f"tecla_X={key} cria_tiro={shot}"
    elif task == "fase2":
        flag = next((n for n in nodes if "bandeira" in str(n.get("name", "")).lower()), None)
        allsrc = " ".join(p.read_text("utf-8", "replace") for p in (project / "scripts").glob("*.luau"))
        scene_ok = (project / "scenes" / "fase2.scene.luau").exists()
        go = "fase2" in allsrc or bool(flag and "fase2" in json.dumps(flag))
        goal = bool(flag) and scene_ok and go
        why = f"bandeira={bool(flag)} cena_fase2={scene_ok} troca={go}"
    elif task == "moedas":
        coins = [n for n in nodes if "moeda" in str(n.get("prefab", ""))]
        goal = len(coins) >= 6
        why = f"moedas={len(coins)} (eram 2)"
    return {"code_ok": code_ok, "game_ok": game_ok, "goal": goal, "detail": why,
            "code": code[-400:] if not code_ok else "", "game_errors": errs[:5]}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(base, path, body=None, timeout=60):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def run_agent(base, text, timeout=900):
    req = urllib.request.Request(base + "/api/agent", data=json.dumps({"chat_id": "eval", "mcp_only": True,
                                 "messages": [{"role": "user", "content": text}]}).encode(), headers={"Content-Type": "application/json"})
    tools, answer, t0 = [], "", time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:])
            except ValueError:
                continue
            a = ev.get("agent") or {}
            if a.get("type") == "tool_start":
                tools.append({"name": a["name"].split("__")[-1]})
            elif a.get("type") == "tool_end" and tools:
                tools[-1]["ok"] = a.get("ok", True) and not str(a.get("result", "")).lower().startswith(("erro", "error"))
            elif a.get("type") == "approval":
                call(base, "/api/agent/approve", {"id": a["id"], "ok": True, "always": True})
            elif a.get("type") == "text":
                answer += a.get("delta", "") or a.get("text", "") or a.get("content", "")
    return {"tools": tools, "seconds": round(time.time() - t0), "answer": answer[-500:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True, help="pasta de dados da Mikoshi com models/ e engine/")
    ap.add_argument("--model", required=True)
    ap.add_argument("--editor", required=True)
    ap.add_argument("--tasks", default=",".join(TASKS))
    ap.add_argument("--ctx", type=int, default=32768)
    ap.add_argument("--out", default="")
    ap.add_argument("--repeat", type=int, default=1, help="rodar cada tarefa N vezes (o modelo varia)")
    ap.add_argument("--keep", default="", help="copiar os projetos testados para esta pasta (para ver o que a IA fez)")
    a = ap.parse_args()
    editor = str(Path(a.editor).expanduser())
    demonic = str(Path(editor).with_name("demonic"))
    tmp = Path(tempfile.mkdtemp(prefix="eval-construct-"))
    home = tmp / "home"
    (home / "data").mkdir(parents=True)
    for d in ("models", "engine"):
        os.symlink(Path(a.home) / d, home / d)
    (home / "data" / "settings.json").write_text(json.dumps({"ctx_size": a.ctx, "use_recommended": True}), "utf-8")
    (home / "data" / "mcp.json").write_text(json.dumps({"servers": [], "construct": {"enabled": True, "auto_approve": True}}), "utf-8")
    recent = tmp / "recentes.txt"
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    results = []
    srv = None
    try:
        for task, rep in [(t, r) for t in a.tasks.split(",") for r in range(a.repeat)]:
            project = tmp / f"proj-{task}-{rep}"
            subprocess.run([demonic, "new", "cena", str(project)], check=True, capture_output=True)
            recent.write_text(str(project) + "\n", "utf-8")
            env = dict(os.environ, LLM_HOME=str(home), LLM_PORT=str(port), ARASAKA_CONSTRUCT_EDITOR=editor,
                       ARASAKA_CONSTRUCT_RECENT=str(recent), PYTHONIOENCODING="utf-8")
            srv = subprocess.Popen([sys.executable, str(APP / "server.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(100):
                try:
                    call(base, "/api/status")
                    break
                except OSError:
                    time.sleep(0.2)
            call(base, "/api/load", {"model": a.model})
            for _ in range(300):
                e = call(base, "/api/status")["engine"]
                if e["state"] in ("ready", "error"):
                    break
                time.sleep(1)
            if e["state"] != "ready":
                raise SystemExit("o modelo nao carregou: " + e.get("error", "")[-300:])
            print(f"== {task} ({rep + 1}/{a.repeat}): rodando...", flush=True)
            run = run_agent(base, TASKS[task])
            res = {"task": task, **run, **check(task, project, editor, demonic)}
            res["score"] = int(res["code_ok"]) + int(res["game_ok"]) + 2 * int(res["goal"])
            fails = sum(1 for t in run["tools"] if not t.get("ok", True))
            print(f"   objetivo={res['goal']} codigo_ok={res['code_ok']} jogo_ok={res['game_ok']} nota={res['score']}/4 "
                  f"ferramentas={len(run['tools'])} (falharam {fails}) {run['seconds']}s | {res['detail']}", flush=True)
            print("   usou: " + ", ".join(t["name"] for t in run["tools"]), flush=True)
            results.append(res)
            if a.keep:
                shutil.copytree(project, Path(a.keep) / project.name, dirs_exist_ok=True)
            call(base, "/api/unload", {"all": True})  # o llama-server e filho: sem isso fica segurando a VRAM
            srv.terminate()
            srv.wait(20)
            srv = None
    finally:
        if srv:
            try:
                call(base, "/api/unload", {"all": True})
            except OSError:
                pass
            srv.terminate()
        total = sum(r["score"] for r in results)
        print(f"TOTAL {total}/{4 * len(results)}")
        if a.out:
            Path(a.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), "utf-8")
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
