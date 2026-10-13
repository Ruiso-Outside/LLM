"""Agentes personalizados e grupos de agentes do LLM Local.

Agente: nome, icone, cor e uma "funcao" (instrucoes). Grupo: sequencia de agentes;
cada um recebe o pedido do usuario e o trabalho dos anteriores. Um agente marcado
como validador termina com "VEREDITO: APROVADO/REPROVADO"; se reprovar, o agente
anterior refaz com o feedback (ate max_retries vezes) e o validador confere de novo.
"""
import json
import re
import time
import uuid
from pathlib import Path

FILE = None
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
VERDICT_RE = re.compile(r"VEREDITO\s*[:\-–]\s*\**\s*(APROVAD[OA]|REPROVAD[OA])", re.I)
THINK_RE = re.compile(r"<think>[\s\S]*?(</think>|$)")
VALIDATOR_SUFFIX = ("\n\nVocê é o VALIDADOR desta etapa. Confira tudo com rigor, refazendo os cálculos ou o raciocínio "
                    "por conta própria. Ao final, escreva em uma linha separada exatamente \"VEREDITO: APROVADO\" se "
                    "estiver tudo correto, ou \"VEREDITO: REPROVADO\" se houver qualquer erro, e explique o motivo em uma frase.")


def configure(data_dir):
    global FILE
    FILE = Path(data_dir) / "agents.json"


def load():
    try:
        return json.loads(FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {"agents": [], "groups": []}


def _s(v, n):
    return str(v or "")[:n]


def save(doc):
    """Valida e grava o documento inteiro de agentes e grupos."""
    agents, ids = [], set()
    for a in (doc.get("agents") or [])[:200]:
        aid = a.get("id") if ID_RE.match(str(a.get("id", ""))) else uuid.uuid4().hex[:10]
        temp = a.get("temperature")
        agents.append({
            "id": aid, "name": _s(a.get("name"), 60) or "Agente", "icon": _s(a.get("icon"), 8) or "🤖",
            "color": _s(a.get("color"), 20) or "#7c6cf2", "instructions": _s(a.get("instructions"), 20000),
            "temperature": None if temp in (None, "") else max(0.0, min(float(temp), 2.0)),
            "web": bool(a.get("web")),
            "model": _s(a.get("model"), 400),  # "" = modelo principal
            "device": a.get("device") if a.get("device") in ("gpu", "cpu") else "auto",
            "kb": a.get("kb") if re.match(r"^[a-f0-9]{10}$", str(a.get("kb") or "")) else "",
        })
        ids.add(aid)
    groups = []
    for g in (doc.get("groups") or [])[:100]:
        gid = g.get("id") if ID_RE.match(str(g.get("id", ""))) else uuid.uuid4().hex[:10]
        steps = [{"agent": s["agent"], "role": "validator" if s.get("role") == "validator" else "agent"}
                 for s in (g.get("steps") or [])[:20] if s.get("agent") in ids]
        groups.append({"id": gid, "name": _s(g.get("name"), 60) or "Grupo", "icon": _s(g.get("icon"), 8) or "👥",
                       "description": _s(g.get("description"), 2000), "steps": steps,
                       "max_retries": max(0, min(int(g.get("max_retries") or 0), 5))})
    out = {"agents": agents, "groups": groups, "updated": time.time()}
    FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    return out


def get_agent(aid):
    return next((a for a in load()["agents"] if a["id"] == aid), None)


def verdict_of(text):
    m = None
    for m in VERDICT_RE.finditer(text or ""):
        pass  # vale o ultimo veredito do texto
    return None if not m else ("APROVADO" if m.group(1).upper().startswith("APROVAD") else "REPROVADO")


def run_group(h, group_id, task_msg, history, sampling):
    """Executa um grupo. h = Handler do servidor (engine_for, engine_call, sse_safe, web_augment, split_content).
    Cada agente usa o proprio modelo (ou o principal), carregado sob demanda pelo gerenciador de modelos."""
    doc = load()
    group = next((g for g in doc["groups"] if g["id"] == group_id), None)
    if not group:
        raise RuntimeError("Grupo não encontrado.")
    agents = {a["id"]: a for a in doc["agents"]}
    steps = [s for s in group["steps"] if s["agent"] in agents]
    if not steps:
        raise RuntimeError("Este grupo não tem agentes. Adicione etapas em Agentes.")

    alive = {"ok": True}

    def emit(obj):
        if alive["ok"]:
            alive["ok"] = h.sse_safe(obj)
        return alive["ok"]

    outputs, feedback, retries = {}, {}, {}
    last_timings, i, n_run, approved = None, 0, 0, None
    while i < len(steps):
        st, ag = steps[i], agents[steps[i]["agent"]]
        is_val = st["role"] == "validator"
        with h.engine_for(ag.get("model", ""), h.loading_notifier(
                lambda name, idx=i: {"group": {"type": "loading", "index": idx, "model": name}}),
                ag.get("device", "auto") if ag.get("model") else "auto") as eng:
            h.engine_port = eng.port
            text, timings = _run_step(h, emit, group, agents, steps, i, ag, is_val, eng, task_msg, history,
                                      outputs, feedback, retries, sampling)
        last_timings = timings or last_timings
        if text is None:  # cliente desconectou
            return last_timings
        outputs[i] = text
        n_run += 1
        verdict = verdict_of(text) if is_val else None
        emit({"group": {"type": "step_end", "index": i, "verdict": verdict}})
        if is_val:
            approved = verdict != "REPROVADO"
            if verdict == "REPROVADO" and i > 0 and retries.get(i - 1, 0) < group["max_retries"]:
                retries[i - 1] = retries.get(i - 1, 0) + 1
                feedback[i - 1] = (outputs.get(i - 1, ""), text)
                emit({"group": {"type": "retry", "index": i - 1, "attempt": retries[i - 1] + 1}})
                i -= 1
                continue
        i += 1
    final = next((outputs[j] for j in range(len(steps) - 1, -1, -1) if j in outputs and steps[j]["role"] != "validator"), "")
    emit({"group": {"type": "done", "final": final, "approved": approved, "steps_run": n_run}})
    return last_timings


def _run_step(h, emit, group, agents, steps, i, ag, is_val, eng, task_msg, history, outputs, feedback, retries, sampling):
    """Executa uma etapa no motor `eng`. Devolve (texto, timings); texto None se o cliente desconectou."""
    system = (ag["instructions"] or "Você é um assistente útil.") + \
        f"\n\nVocê é o agente \"{ag['name']}\" do grupo \"{group['name']}\"." + \
        (f" Objetivo do grupo: {group['description']}" if group["description"] else "") + \
        " Faça somente a sua função, sem repetir o trabalho dos outros agentes. Responda no idioma do usuário." + \
        (VALIDATOR_SUFFIX if is_val else "") + (("\n\n" + h.reply_rule()) if h.reply_rule() else "")
    task_text, task_parts = h.split_content(task_msg, eng.modalities)
    user = f"Pedido do usuário:\n{task_text}"
    prev = [(steps[j], outputs[j]) for j in range(i) if j in outputs]
    if prev:
        user += "\n\nTrabalho dos agentes anteriores:\n\n" + "\n\n".join(
            f"### {agents[s['agent']]['icon']} {agents[s['agent']]['name']}\n{text}" for s, text in prev)
    if i in feedback:
        old, fb = feedback.pop(i)
        user += (f"\n\nSua resposta anterior foi REPROVADA pelo validador.\n\nSua resposta anterior:\n{old}"
                 f"\n\nFeedback do validador:\n{fb}\n\nRefaça a sua parte corrigindo os problemas apontados.")
    content = task_parts + [{"type": "text", "text": user}] if task_parts else user
    messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": content}]
    model_name = Path(eng.model).stem if eng.model else ""
    if not emit({"group": {"type": "step_start", "index": i, "agent": {k: ag[k] for k in ("id", "name", "icon", "color")},
                           "role": steps[i]["role"], "attempt": retries.get(i, 0) + 1, "model": model_name,
                           "device": eng.device}}):
        return None, None
    if ag.get("kb"):
        messages = h.kb_augment(messages, ag["kb"])
    if ag["web"]:
        messages = h.web_augment(messages)
    payload = {"messages": messages, "stream": True, "cache_prompt": True, "timings_per_token": True, **sampling}
    h.apply_model_sampling(payload, eng.model, ag["temperature"])
    text, timings = "", None
    with h.engine_call(payload, True) as up:
        for raw in iter(up.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            try:
                j = json.loads(line[5:])
            except ValueError:
                continue
            if j.get("timings"):
                timings = j["timings"]
                emit({"timings": j["timings"]})
            d = ((j.get("choices") or [{}])[0].get("delta") or {})
            if d.get("reasoning_content"):
                emit({"group": {"type": "reasoning", "delta": d["reasoning_content"]}})
            if d.get("content"):
                text += d["content"]
                if not emit({"group": {"type": "delta", "delta": d["content"]}}):
                    return None, timings
    return THINK_RE.sub("", text).strip(), timings


# ---------------------------------------------------------------- modelos prontos

def _ag(name, icon, color, instructions, web=False, temperature=None):
    return {"id": uuid.uuid4().hex[:10], "name": name, "icon": icon, "color": color, "instructions": instructions,
            "web": web, "temperature": temperature}


def template(kind):
    if kind == "math":
        a = [_ag("Criador de cálculos", "🧮", "#4fc3f7",
                 "Você cria UM problema de matemática claro e bem definido, de acordo com o tema e o nível pedidos pelo "
                 "usuário (se ele não disser, escolha algo de nível médio). Apresente apenas o enunciado, com todos os dados "
                 "necessários. NÃO resolva o problema.", temperature=0.9),
             _ag("Resolvedor", "✏️", "#7c6cf2",
                 "Você resolve o problema criado pelo agente anterior. Mostre o passo a passo de forma clara e organizada, "
                 "com as contas, e termine com a resposta final destacada em negrito.", temperature=0.3),
             _ag("Validador", "✅", "#3ecf8e",
                 "Você confere se o enunciado faz sentido e se a resolução e a resposta final estão corretas. Refaça as "
                 "contas por conta própria, de outro jeito se possível, e aponte exatamente onde estiver qualquer erro.",
                 temperature=0.1)]
        g = {"name": "Matemática", "icon": "🧮", "description": "Cria um cálculo, resolve passo a passo e valida o resultado.",
             "max_retries": 2, "roles": ["agent", "agent", "validator"]}
    elif kind == "writing":
        a = [_ag("Pesquisador", "🔎", "#f2b84b",
                 "Você levanta os fatos, dados e pontos principais sobre o tema pedido pelo usuário, em tópicos curtos e "
                 "objetivos. Não escreva o texto final.", web=True, temperature=0.3),
             _ag("Redator", "📝", "#7c6cf2",
                 "Você escreve o texto pedido pelo usuário usando os pontos levantados pelo pesquisador: bem estruturado, "
                 "com título, introdução, desenvolvimento e conclusão, em linguagem clara.", temperature=0.7),
             _ag("Revisor", "🧐", "#3ecf8e",
                 "Você revisa o texto do redator: gramática, clareza, coerência e se os fatos batem com a pesquisa. "
                 "Liste os problemas encontrados de forma específica.", temperature=0.2)]
        g = {"name": "Redação", "icon": "📝", "description": "Pesquisa o tema, escreve o texto e revisa.",
             "max_retries": 1, "roles": ["agent", "agent", "validator"]}
    elif kind == "code":
        a = [_ag("Planejador", "🗺️", "#f2b84b",
                 "Você transforma o pedido do usuário em um plano técnico curto: requisitos, estrutura de arquivos/funções "
                 "e passos. Não escreva o código.", temperature=0.4),
             _ag("Programador", "💻", "#7c6cf2",
                 "Você implementa o plano do planejador escrevendo código completo, funcional e comentado, em blocos de "
                 "código com o nome de cada arquivo.", temperature=0.2),
             _ag("Revisor de código", "🔍", "#3ecf8e",
                 "Você revisa o código do programador procurando bugs, casos não tratados, problemas de segurança e se ele "
                 "cumpre o pedido. Seja específico sobre o que corrigir.", temperature=0.1)]
        g = {"name": "Programação", "icon": "💻", "description": "Planeja, programa e revisa o código.",
             "max_retries": 2, "roles": ["agent", "agent", "validator"]}
    else:
        raise ValueError("modelo desconhecido")
    group = {"id": uuid.uuid4().hex[:10], "name": g["name"], "icon": g["icon"], "description": g["description"],
             "max_retries": g["max_retries"], "steps": [{"agent": x["id"], "role": r} for x, r in zip(a, g["roles"])]}
    doc = load()
    doc["agents"] += a
    doc["groups"].append(group)
    return save(doc), group["id"]
