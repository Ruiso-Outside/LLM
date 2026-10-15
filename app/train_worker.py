"""Treino do Piphin LLM: fine-tuning LoRA/QLoRA e exportacao para GGUF.

Roda no ambiente Python proprio do treino (engine/train/venv, com PyTorch + CUDA), chamado pelo servidor:
    python train_worker.py probe
    python train_worker.py train  <config.json>
    python train_worker.py export <config.json>
Cada evento sai como uma linha JSON no stdout (o servidor le e mostra no Estudio de treino).
Com PIPHIN_TRAIN_FAKE=1 simula o treino sem PyTorch (usado nos testes automaticos).
"""
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

FAKE = os.environ.get("PIPHIN_TRAIN_FAKE") == "1"


def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def dir_size(p):
    p = Path(p)
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else (p.stat().st_size if p.exists() else 0)


def load_examples(path):
    out = []
    for line in Path(path).read_text("utf-8").splitlines():
        if line.strip():
            ex = json.loads(line)
            if ex.get("messages") and ex.get("status", "approved") == "approved":
                out.append(ex["messages"])
    return out


# ---------------------------------------------------------------- probe

def probe():
    if FAKE:
        return emit({"type": "probe", "ok": True, "torch": "fake", "cuda": True, "device": "GPU de teste", "vram_gb": 16, "bnb": True})
    info = {"type": "probe", "python": sys.version.split()[0]}
    try:
        import torch
        info.update(torch=torch.__version__, cuda=torch.cuda.is_available(), cuda_version=torch.version.cuda)
        if torch.cuda.is_available():
            info.update(device=torch.cuda.get_device_name(0), vram_gb=round(torch.cuda.get_device_properties(0).total_memory / 2 ** 30, 1),
                        capability=".".join(map(str, torch.cuda.get_device_capability(0))))
            x = torch.ones(256, 256, device="cuda") @ torch.ones(256, 256, device="cuda")  # a placa roda de verdade?
            info["matmul_ok"] = bool(x[0, 0].item() == 256)
    except Exception as e:  # noqa: BLE001
        info.update(ok=False, error=f"PyTorch: {e}")
        return emit(info)
    try:
        import bitsandbytes  # noqa: F401
        info["bnb"] = True
    except Exception as e:  # noqa: BLE001
        info.update(bnb=False, bnb_error=str(e)[:300])
    info["ok"] = bool(info.get("cuda"))
    emit(info)


# ---------------------------------------------------------------- treino

def fake_train(cfg):
    run = Path(cfg["run_dir"])
    n = len(load_examples(cfg["dataset"]))
    steps = max(4, math.ceil(n * cfg.get("epochs", 1) / (cfg.get("batch_size", 1) * cfg.get("grad_accum", 4))))
    if cfg.get("parent_adapter"):
        if not (Path(cfg["parent_adapter"]) / "adapter_config.json").is_file():
            raise RuntimeError("adaptador anterior não encontrado")
        emit({"type": "info", "phase": "model", "msg": f"Continuando o treino de {cfg.get('parent_name')}..."})
    emit({"type": "setup", "total_params": 4_022_468_096, "trainable_params": 33_030_144, "trainable_pct": 0.82,
          "lora_r": cfg["lora_r"], "lora_alpha": cfg["lora_alpha"], "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
          "train_examples": n, "eval_examples": 1, "train_tokens": n * 300, "total_steps": steps, "quant": "4-bit NF4",
          "compute_dtype": "bfloat16", "device": "GPU de teste", "vram_total": 16 * 2 ** 30, "max_len": cfg["max_len"]})
    t0 = time.time()
    for s in range(1, steps + 1):
        if (run / "STOP").exists():
            emit({"type": "info", "msg": "Parado pelo usuario."})
            break
        time.sleep(0.05)
        loss = 2.4 * math.exp(-s / steps * 1.5) + 0.3
        emit({"type": "step", "step": s, "total_steps": steps, "epoch": s / steps * cfg.get("epochs", 1), "loss": round(loss, 4),
              "lr": cfg["lr"] * min(1, s / 2), "grad_norm": 0.8, "tokens": s * 600, "tok_s": 1200.0, "step_time": 0.05,
              "mem_alloc": 5 * 2 ** 30, "mem_reserved": 6 * 2 ** 30, "mem_peak": 6.5 * 2 ** 30,
              "eta_s": (steps - s) * 0.05, "elapsed_s": time.time() - t0})
        if s % max(1, cfg.get("eval_every", 2)) == 0:
            emit({"type": "eval", "step": s, "eval_loss": round(loss + 0.1, 4), "ppl": round(math.exp(loss + 0.1), 3)})
    adapter = run / "adapter"
    adapter.mkdir(parents=True, exist_ok=True)
    (adapter / "adapter_model.safetensors").write_bytes(b"0" * 1024)
    (adapter / "adapter_config.json").write_text(json.dumps({"base_model_name_or_path": cfg["base_repo"], "r": cfg["lora_r"]}), "utf-8")
    emit({"type": "done", "adapter_dir": str(adapter), "adapter_size": dir_size(adapter), "final_loss": 0.4,
          "best_eval": 0.5, "duration_s": time.time() - t0})


def train(cfg):
    if FAKE:
        return fake_train(cfg)
    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, get_cosine_schedule_with_warmup

    run = Path(cfg["run_dir"])
    token = cfg.get("hf_token") or None
    random.seed(cfg.get("seed", 42))
    torch.manual_seed(cfg.get("seed", 42))
    emit({"type": "info", "phase": "tokenizer", "msg": f"Carregando o tokenizer de {cfg['base_repo']}..."})
    tok = AutoTokenizer.from_pretrained(cfg["base_repo"], token=token, trust_remote_code=False)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    # -- dados: so a resposta do assistente entra no calculo do erro (o pedido fica mascarado)
    examples = load_examples(cfg["dataset"])
    if len(examples) < 2:
        raise RuntimeError("O conjunto de dados precisa de pelo menos 2 exemplos aprovados.")
    random.shuffle(examples)
    n_eval = max(1, int(len(examples) * cfg.get("eval_ratio", 0.05))) if len(examples) >= 10 else 1
    max_len = int(cfg.get("max_len", 2048))

    def encode(msgs):
        full = tok.apply_chat_template(msgs, tokenize=False)
        prompt = tok.apply_chat_template(msgs[:-1], tokenize=False, add_generation_prompt=True)
        ids = tok(full, add_special_tokens=False, truncation=True, max_length=max_len)["input_ids"]
        n_prompt = len(tok(prompt, add_special_tokens=False)["input_ids"])
        labels = [-100] * min(n_prompt, len(ids)) + ids[n_prompt:]
        return {"input_ids": ids, "labels": labels[:len(ids)]}

    enc = [encode(m) for m in examples]
    enc = [e for e in enc if any(l != -100 for l in e["labels"])]
    eval_set, train_set = enc[:n_eval], enc[n_eval:] or enc[:1]
    train_tokens = sum(len(e["input_ids"]) for e in train_set)

    # -- modelo em 4 bits (QLoRA) + adaptadores LoRA
    emit({"type": "info", "phase": "model", "msg": "Baixando/carregando o modelo base em 4 bits (a primeira vez demora)..."})
    compute = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                               bnb_4bit_compute_dtype=compute) if cfg.get("quant4bit", True) else None
    model = AutoModelForCausalLM.from_pretrained(cfg["base_repo"], token=token, quantization_config=quant,
                                                 torch_dtype=compute, device_map={"": 0}, attn_implementation="sdpa")
    model.config.use_cache = False
    if quant:
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    else:
        model.gradient_checkpointing_enable()
    if cfg.get("parent_adapter"):
        # continua de onde a IA parou: o mesmo adaptador LoRA segue aprendendo com o conteudo novo
        from peft import PeftModel
        emit({"type": "info", "phase": "model", "msg": f"Continuando o treino de {cfg.get('parent_name') or 'uma IA já treinada'}..."})
        model = PeftModel.from_pretrained(model, cfg["parent_adapter"], is_trainable=True)
        lcfg = model.peft_config["default"]
    else:
        lcfg = LoraConfig(r=int(cfg["lora_r"]), lora_alpha=int(cfg["lora_alpha"]), lora_dropout=float(cfg.get("lora_dropout", 0.05)),
                          target_modules=cfg.get("target_modules") or "all-linear", bias="none", task_type="CAUSAL_LM")
        model = get_peft_model(model, lcfg)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() * (2 if getattr(p, "quant_type", None) else 1) for p in model.parameters())  # 4 bits guardam 2 valores por byte
    bs, accum, epochs = int(cfg.get("batch_size", 1)), int(cfg.get("grad_accum", 4)), float(cfg.get("epochs", 2))
    steps_per_epoch = max(1, math.ceil(len(train_set) / (bs * accum)))
    total_steps = max(1, int(steps_per_epoch * epochs))
    targets = sorted(lcfg.target_modules) if isinstance(lcfg.target_modules, (set, list)) else [str(lcfg.target_modules)]
    emit({"type": "setup", "total_params": total, "trainable_params": trainable, "trainable_pct": round(trainable / total * 100, 3),
          "lora_r": lcfg.r, "lora_alpha": lcfg.lora_alpha, "target_modules": targets, "train_examples": len(train_set),
          "eval_examples": len(eval_set), "train_tokens": train_tokens, "total_steps": total_steps, "continued": bool(cfg.get("parent_adapter")),
          "quant": "4-bit NF4 (QLoRA)" if quant else "sem quantização", "compute_dtype": str(compute).replace("torch.", ""),
          "device": torch.cuda.get_device_name(0), "vram_total": torch.cuda.get_device_properties(0).total_memory, "max_len": max_len})

    try:
        import bitsandbytes as bnb
        opt = bnb.optim.PagedAdamW8bit([p for p in model.parameters() if p.requires_grad], lr=float(cfg["lr"]), weight_decay=0.0)
    except Exception:  # noqa: BLE001
        opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=float(cfg["lr"]), weight_decay=0.0)
    sched = get_cosine_schedule_with_warmup(opt, int(total_steps * cfg.get("warmup_ratio", 0.05)), total_steps)

    def batches(data, shuffle):
        idx = list(range(len(data)))
        if shuffle:
            random.shuffle(idx)
        for i in range(0, len(idx), bs):
            group = [data[j] for j in idx[i:i + bs]]
            n = max(len(g["input_ids"]) for g in group)
            ids = torch.tensor([g["input_ids"] + [tok.pad_token_id] * (n - len(g["input_ids"])) for g in group])
            lab = torch.tensor([g["labels"] + [-100] * (n - len(g["labels"])) for g in group])
            att = torch.tensor([[1] * len(g["input_ids"]) + [0] * (n - len(g["input_ids"])) for g in group])
            yield ids.cuda(), lab.cuda(), att.cuda()

    @torch.no_grad()
    def evaluate():
        model.eval()
        losses = [model(input_ids=i, labels=l, attention_mask=a).loss.item() for i, l, a in batches(eval_set, False)]
        model.train()
        return sum(losses) / max(1, len(losses))

    model.train()
    torch.cuda.reset_peak_memory_stats()
    t0, step, tokens, best_eval, last_loss = time.time(), 0, 0, None, None
    stopped = False
    eval_every, save_every = int(cfg.get("eval_every", 25)), int(cfg.get("save_every", 100))
    while step < total_steps and not stopped:
        micro, acc_loss, acc_tokens, ts = 0, 0.0, 0, time.time()
        for ids, lab, att in batches(train_set, True):
            out = model(input_ids=ids, labels=lab, attention_mask=att)
            (out.loss / accum).backward()
            acc_loss += out.loss.item()
            acc_tokens += int(att.sum().item())
            micro += 1
            if micro % accum:
                continue
            gn = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0).item()
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            tokens += acc_tokens
            dt = time.time() - ts
            elapsed = time.time() - t0
            last_loss = acc_loss / accum
            emit({"type": "step", "step": step, "total_steps": total_steps, "epoch": round(step / steps_per_epoch, 3),
                  "loss": round(last_loss, 5), "lr": sched.get_last_lr()[0], "grad_norm": round(gn, 4), "tokens": tokens,
                  "tok_s": round(acc_tokens / dt, 1) if dt else 0, "step_time": round(dt, 3),
                  "mem_alloc": torch.cuda.memory_allocated(), "mem_reserved": torch.cuda.memory_reserved(),
                  "mem_peak": torch.cuda.max_memory_allocated(), "elapsed_s": round(elapsed, 1),
                  "eta_s": round(elapsed / step * (total_steps - step), 1)})
            acc_loss, acc_tokens, ts = 0.0, 0, time.time()
            if step % eval_every == 0 or step == total_steps:
                ev = evaluate()
                best_eval = ev if best_eval is None else min(best_eval, ev)
                emit({"type": "eval", "step": step, "eval_loss": round(ev, 5), "ppl": round(math.exp(min(ev, 20)), 3)})
            if step % save_every == 0 and step < total_steps:
                ck = run / "checkpoint"
                model.save_pretrained(ck)
                emit({"type": "checkpoint", "step": step, "path": str(ck), "size": dir_size(ck)})
            if (run / "STOP").exists():
                emit({"type": "info", "msg": "Parado pelo usuário: salvando o que foi treinado até aqui."})
                stopped = True
                break
            if step >= total_steps:
                break
    adapter = run / "adapter"
    model.save_pretrained(adapter)
    tok.save_pretrained(adapter)
    shutil.rmtree(run / "checkpoint", ignore_errors=True)
    emit({"type": "done", "adapter_dir": str(adapter), "adapter_size": dir_size(adapter), "final_loss": last_loss,
          "best_eval": best_eval, "duration_s": round(time.time() - t0, 1), "stopped": stopped})


# ---------------------------------------------------------------- exportacao para GGUF

def export(cfg):
    run = Path(cfg["run_dir"])
    out = Path(cfg["out_path"])
    out.parent.mkdir(parents=True, exist_ok=True)
    if FAKE:
        out.write_bytes(b"GGUF" + b"0" * 2048)
        return emit({"type": "export", "stage": "done", "out_path": str(out), "size": out.stat().st_size, "params": 4_022_468_096})
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    merged = run / "merged"
    shutil.rmtree(merged, ignore_errors=True)
    emit({"type": "export", "stage": "merge", "msg": "Juntando o LoRA ao modelo base (na RAM, em bf16)..."})
    base = AutoModelForCausalLM.from_pretrained(cfg["base_repo"], token=cfg.get("hf_token") or None, torch_dtype=torch.bfloat16,
                                                device_map={"": "cpu"}, low_cpu_mem_usage=True)
    model = PeftModel.from_pretrained(base, run / "adapter").merge_and_unload()
    params = sum(p.numel() for p in model.parameters())
    model.save_pretrained(merged, safe_serialization=True, max_shard_size="4GB")
    AutoTokenizer.from_pretrained(run / "adapter").save_pretrained(merged)
    del model, base
    f16 = run / "model-f16.gguf"
    emit({"type": "export", "stage": "convert", "msg": "Convertendo para GGUF (f16)..."})
    p = subprocess.run([sys.executable, cfg["convert_script"], str(merged), "--outfile", str(f16), "--outtype", "f16"],
                       capture_output=True, text=True)
    if p.returncode != 0 or not f16.exists():
        raise RuntimeError("Falha na conversão para GGUF: " + (p.stderr or p.stdout)[-1200:])
    shutil.rmtree(merged, ignore_errors=True)
    q = cfg.get("quant_type", "Q4_K_M")
    if q.upper() in ("F16", "NONE"):
        shutil.move(str(f16), str(out))
    else:
        emit({"type": "export", "stage": "quantize", "msg": f"Quantizando para {q}..."})
        for attempt in range(2):  # o antivirus pode segurar o arquivo recem-criado por alguns instantes
            p = subprocess.run([cfg["quantize_exe"], str(f16), str(out), q], capture_output=True, text=True,
                               cwd=str(Path(cfg["quantize_exe"]).parent))
            if p.returncode == 0 and out.exists():
                break
            time.sleep(5)
        if p.returncode != 0 or not out.exists():
            raise RuntimeError(f"Falha ao quantizar (código {p.returncode & 0xffffffff:#x}, saída existe: {out.exists()}): "
                               + (p.stderr or p.stdout)[-1200:] + f" | comando: {cfg['quantize_exe']} {f16} {out} {q}")
        f16.unlink(missing_ok=True)
    emit({"type": "export", "stage": "done", "out_path": str(out), "size": out.stat().st_size, "params": params})


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    try:
        if cmd == "probe":
            return probe()
        cfg = json.loads(Path(sys.argv[2]).read_text("utf-8"))
        {"train": train, "export": export}[cmd](cfg)
    except Exception as e:  # noqa: BLE001
        emit({"type": "error", "msg": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-3000:]})
        sys.exit(1)


if __name__ == "__main__":
    main()
