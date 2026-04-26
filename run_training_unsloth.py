"""OpenGrid GRPO Training Runner — Unsloth variant.

This is the Unsloth-accelerated version of run_training.py. It uses
unsloth.FastLanguageModel for ~2x faster training and lower memory at
the same configuration. Functionality is otherwise identical:
env-grounded GRPO, baseline + post-training eval, plots, summary.json.

Why two scripts?
- run_training.py             : transformers + bitsandbytes + peft (used for the shipped run)
- run_training_unsloth.py     : unsloth-accelerated path (alternative, faster GPU pipeline)

Choose whichever stack works for your GPU/runtime. Both produce the same
training/outputs/summary.json schema.
"""
import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
import sys
import json
import copy
import time
import shutil
import traceback
from pathlib import Path

# --- TRITON COMPILER FIX ---
import subprocess
try:
    print("Checking for gcc...")
    result = subprocess.run(['which', 'gcc'], capture_output=True, text=True)
    gcc_path = result.stdout.strip()
    print(f"gcc location: {gcc_path or 'NOT FOUND'}")
    if gcc_path:
        os.environ['CC'] = gcc_path
        os.environ['CXX'] = shutil.which('g++') or ''
        result2 = subprocess.run(['gcc', '--version'], capture_output=True, text=True)
        print(f"gcc version:\n{result2.stdout.strip()[:100]}")
    else:
        print("WARNING: gcc still not found in PATH!")
except Exception as e:
    print(f"Error checking gcc: {e}")
# ----------------------------


# ── Training ──────────────────────────────────────────────────────
def run_grpo_training():
    """Run GRPO training with env-grounded rewards, accelerated by Unsloth."""
    # IMPORTANT: Unsloth must be imported BEFORE transformers/trl to apply its patches.
    from unsloth import FastLanguageModel, is_bfloat16_supported

    import torch
    import numpy as np

    print("=" * 60)
    print("  OpenGrid GRPO Training — Unsloth")
    print("=" * 60)

    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    else:
        print("WARNING: No GPU detected — Unsloth requires CUDA. Aborting.")
        raise RuntimeError("Unsloth requires a CUDA-capable GPU.")

    # Import project modules
    sys.path.insert(0, ".")
    from src.environment import OpenGridEnv
    from src.tasks import TASKS
    from src.models import GridAction, BusAdjustment
    from training.train_grpo import (
        SYSTEM_PROMPT, format_observation_prompt,
        compute_grpo_reward_env, extract_action,
        rollout_multi_agent,
    )

    # ── 1. Load model with Unsloth ──
    print("\n[1/6] Loading model with Unsloth (4-bit)...")

    # ── Iteration-budget config ── tweak to trade speed vs quality ──
    MODEL_NAME    = "unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit"  # pre-quantized for fast load
    LORA_RANK     = 8       # 8 → faster, less VRAM; 16 → more capacity
    NUM_EPOCHS    = 1       # 1 epoch ≈ 25-30 min on Unsloth (vs ~50 min on bnb)
    NUM_EPISODES  = 4       # prompt generation episodes
    SAVE_STEPS    = 25
    MAX_SEQ_LEN   = 1024    # prompt+completion budget; Unsloth pre-allocates this
    # ──────────────────────────────────────────────────────────────

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LEN,
        dtype=None,             # auto-detect bf16/fp16
        load_in_4bit=True,
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Unsloth's PEFT wrapper — handles all the bnb-4bit + LoRA + grad checkpointing
    # plumbing internally, so no separate prepare_model_for_kbit_training step.
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_RANK,
        lora_alpha=LORA_RANK * 2,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        bias="none",
        use_gradient_checkpointing="unsloth",  # Unsloth's optimized variant
        random_state=42,
        use_rslora=False,
        loftq_config=None,
    )
    model.config.pad_token_id = tokenizer.pad_token_id

    print(f"  Model: {MODEL_NAME}")
    print(f"  Trainable params: {sum(p.numel() for p in model.parameters() if p.requires_grad):,}")

    # ── 2. Baseline evaluation ──
    print("\n[2/6] Running baseline evaluation...")
    import re

    def heuristic_generate(prompt):
        freq_match = re.search(r'Frequency: ([\d.]+)', prompt)
        freq = float(freq_match.group(1)) if freq_match else 50.0
        error = 50.0 - freq
        delta = max(-20, min(20, error * 10))
        bus_match = re.search(r'Bus (\d+) \((generator|battery|slack)\)', prompt)
        if bus_match:
            return json.dumps({"bus_adjustments": [{"bus_id": int(bus_match.group(1)), "delta": round(delta, 1)}], "topology_actions": []})
        return json.dumps({"bus_adjustments": [], "topology_actions": []})

    baseline_results = {}
    for task_id in ["task_easy", "task_medium", "karnataka_easy", "karnataka_medium", "karnataka_hard", "task_karnataka"]:
        if task_id not in TASKS:
            continue
        config = TASKS[task_id]
        rewards = []
        for ep in range(3):
            ep_config = copy.deepcopy(config)
            ep_config['seed'] = 42 + ep
            env = OpenGridEnv(ep_config)
            result = rollout_multi_agent(env, heuristic_generate, ep_config)
            rewards.append(result['total_reward'])
        baseline_results[task_id] = {"avg": np.mean(rewards), "std": np.std(rewards), "rewards": rewards}
        print(f"  [BASELINE] {task_id}: {np.mean(rewards):.2f} ± {np.std(rewards):.2f}")

    # ── 3. Generate training prompts ──
    print("\n[3/6] Generating training prompts...")
    TRAIN_TASK = "task_karnataka" if "task_karnataka" in TASKS else "task_easy"
    task_config = copy.deepcopy(TASKS[TRAIN_TASK])
    base_seed = task_config.get('seed', 42)

    prompts = []
    obs_contexts = []
    rng = np.random.RandomState(base_seed)

    for episode in range(NUM_EPISODES):
        ep_config = copy.deepcopy(task_config)
        ep_config['seed'] = base_seed + episode
        env = OpenGridEnv(ep_config)
        zone_obs = env.reset_multi()

        if episode % 5 == 0:
            for b in env.bus_state:
                b_cfg = env._find_bus_config(b['id'])
                if b_cfg and b_cfg['type'] == 'battery':
                    b['soc'] = max(1.0, b['soc'] * 0.1)

        for t in range(min(15, task_config['max_steps'])):
            for agent_id, obs in zone_obs.items():
                obs_dict = json.loads(obs.model_dump_json())
                prompt_text = format_observation_prompt(obs_dict, zone_name=obs.zone_name)
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt_text},
                ]
                formatted = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                prompts.append(formatted)
                obs_contexts.append(json.dumps(obs_dict))

            random_actions = {}
            for aid in range(env.num_agents):
                zone_buses = task_config['zone_bus_ids'].get(aid, [])
                controllable = [
                    bid for bid in zone_buses
                    if next((b for b in task_config['buses'] if b['id'] == bid), {}).get('type')
                    in ['generator', 'battery']
                ]
                adj = []
                if controllable:
                    n_adj = min(len(controllable), rng.randint(1, 3))
                    chosen = rng.choice(controllable, size=n_adj, replace=False)
                    for bid in chosen:
                        adj.append(BusAdjustment(bus_id=int(bid), delta=float(rng.uniform(-30, 30))))
                random_actions[aid] = GridAction(bus_adjustments=adj)

            result = env.step_multi(random_actions)
            if result.done:
                break
            zone_obs = result.observations

    print(f"  Generated {len(prompts)} training prompts")

    # ── 4. Train ──
    print("\n[4/6] Starting GRPO training...")
    from trl import GRPOTrainer, GRPOConfig
    from datasets import Dataset
    import inspect as _inspect
    _grpo_params = set(_inspect.signature(GRPOConfig.__init__).parameters)

    _bf16 = is_bfloat16_supported()
    _fp16 = not _bf16

    def reward_fn(completions, obs_context=None, **kwargs):
        texts = []
        for c in completions:
            if isinstance(c, list):
                text = c[-1]['content'] if c else ""
            else:
                text = str(c)
            texts.append(text)

        if obs_context is None:
            obs_context = [None] * len(texts)

        obs_dicts = []
        for ctx in obs_context:
            if isinstance(ctx, str):
                try:
                    obs_dicts.append(json.loads(ctx))
                except (json.JSONDecodeError, TypeError):
                    obs_dicts.append(None)
            else:
                obs_dicts.append(ctx)

        return compute_grpo_reward_env(texts, obs_dicts, task_config)

    from transformers import GenerationConfig
    model.generation_config = GenerationConfig(
        do_sample=True,
        temperature=0.7,
        top_p=0.9,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
        max_new_tokens=64,
    )

    # Some GRPOConfig params were renamed/moved between TRL versions; only pass
    # what this installed TRL accepts.
    _opt = {}
    if 'max_prompt_length'     in _grpo_params: _opt['max_prompt_length']     = 512
    if 'max_completion_length' in _grpo_params: _opt['max_completion_length'] = 64
    if 'torch_compile'         in _grpo_params: _opt['torch_compile']         = False
    if 'use_vllm'              in _grpo_params: _opt['use_vllm']              = False

    grpo_config = GRPOConfig(
        output_dir="training/outputs/grpo_checkpoints_unsloth",
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        learning_rate=2e-5,
        logging_steps=1,
        save_steps=SAVE_STEPS,
        save_total_limit=3,
        num_generations=4,
        report_to="none",
        remove_unused_columns=False,
        bf16=_bf16,
        fp16=_fp16,
        gradient_checkpointing=False,  # Unsloth handles this internally
        optim="paged_adamw_8bit",
        warmup_ratio=0.05,
        lr_scheduler_type="cosine",
        dataloader_num_workers=0,
        **_opt,
    )

    train_dataset = Dataset.from_dict({"prompt": prompts, "obs_context": obs_contexts})
    print(f"  Dataset: {len(train_dataset)} rows")
    print(f"  Effective batch: {grpo_config.per_device_train_batch_size * grpo_config.gradient_accumulation_steps}")

    # Switch Unsloth into training mode (it has a separate inference fast-path)
    FastLanguageModel.for_training(model)

    trainer = GRPOTrainer(
        model=model, args=grpo_config, train_dataset=train_dataset,
        reward_funcs=reward_fn, processing_class=tokenizer,
    )

    # Sanity-check generation
    print("  [DEBUG] Testing model generation (should complete in <30s)...")
    _test_inputs = tokenizer("Hello", return_tensors="pt").to(model.device)
    with torch.no_grad():
        _out = model.generate(
            **_test_inputs,
            max_new_tokens=8,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    print(f"  [DEBUG] Generation OK: {tokenizer.decode(_out[0][-8:], skip_special_tokens=True)!r}")

    print("  [NOTE] First GRPO step may include Triton JIT compilation. That is normal.")
    t0 = time.time()
    trainer.train()
    train_time = time.time() - t0
    print(f"\n  Training complete in {train_time/60:.1f} minutes")

    # Save adapter only
    output_path = "training/outputs/trained_model_unsloth"
    os.makedirs(output_path, exist_ok=True)
    torch.cuda.empty_cache()
    try:
        model.save_pretrained(output_path)
        tokenizer.save_pretrained(output_path)
        print(f"  Adapter saved to {output_path}")
    except Exception as save_err:
        print(f"  WARNING: adapter save failed ({save_err}); training metrics still captured")

    # ── 5. Post-training evaluation ──
    print("\n[5/6] Evaluating trained model (fast: 3 tasks × 1 ep)...")
    torch.cuda.empty_cache()

    # Switch Unsloth to inference mode for ~2x generation speed
    FastLanguageModel.for_inference(model)

    def trained_generate(prompt):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        formatted = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(formatted, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outputs = model.generate(
                **inputs, max_new_tokens=64,
                temperature=0.3, do_sample=True,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        return tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)

    trained_results = {}
    EVAL_TASKS = ["task_easy", "task_karnataka", "karnataka_hard"]
    for task_id in EVAL_TASKS:
        if task_id not in TASKS:
            continue
        try:
            config = TASKS[task_id]
            ep_config = copy.deepcopy(config)
            ep_config['seed'] = 42
            env = OpenGridEnv(ep_config)
            result = rollout_multi_agent(env, trained_generate, ep_config)
            r = result['total_reward']
            trained_results[task_id] = {"avg": round(r, 2), "std": 0.0, "rewards": [r]}
            print(f"  [TRAINED] {task_id}: {r:.2f}")
            torch.cuda.empty_cache()
        except Exception as eval_err:
            print(f"  [TRAINED] {task_id}: eval failed ({eval_err})")
            trained_results[task_id] = {"avg": None, "std": None, "rewards": []}

    # ── 6. Generate plots ──
    print("\n[6/6] Generating plots...")
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs("training/outputs", exist_ok=True)

    # Before vs After
    common_tasks = [t for t in baseline_results if t in trained_results]
    if common_tasks:
        fig, ax = plt.subplots(figsize=(10, 6))
        x = np.arange(len(common_tasks))
        width = 0.35
        before = [baseline_results[t]['avg'] for t in common_tasks]
        after = [trained_results[t]['avg'] for t in common_tasks]
        ax.bar(x - width/2, before, width, label='Heuristic Baseline', color='#ff6b6b', alpha=0.8)
        ax.bar(x + width/2, after, width, label='GRPO Trained (Unsloth)', color='#00d4aa', alpha=0.8)
        ax.set_xlabel('Task'); ax.set_ylabel('Average Episode Reward')
        ax.set_title('OpenGrid — GRPO Training (Unsloth): Before vs After', fontweight='bold')
        ax.set_xticks(x); ax.set_xticklabels([t.replace('task_', '').title() for t in common_tasks])
        ax.legend(); ax.grid(True, alpha=0.3, axis='y')
        for bars in ax.containers:
            for bar in bars:
                h = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., h + (1 if h >= 0 else -3),
                        f'{h:.1f}', ha='center', va='bottom' if h >= 0 else 'top', fontsize=10)
        plt.tight_layout()
        plt.savefig('training/outputs/before_after_unsloth.png', dpi=150)
        plt.close()

    # Training loss
    history = trainer.state.log_history
    steps = [h['step'] for h in history if 'loss' in h]
    losses = [h['loss'] for h in history if 'loss' in h]
    if steps:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(steps, losses, color='#ff6b6b', linewidth=1.5, alpha=0.6, label='Loss')
        if len(losses) > 10:
            w = min(20, len(losses) // 3)
            smoothed = np.convolve(losses, np.ones(w)/w, mode='valid')
            ax.plot(steps[w-1:], smoothed, color='#ff6b6b', linewidth=2.5, label=f'Smoothed (w={w})')
        ax.set_xlabel('Step'); ax.set_ylabel('Loss')
        ax.set_title('OpenGrid GRPO (Unsloth) — Training Loss', fontweight='bold')
        ax.legend(); ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig('training/outputs/training_loss_unsloth.png', dpi=150)
        plt.close()

    # Save summary — same schema as the bnb run, with framework field updated
    log_history = trainer.state.log_history
    summary = {
        "model": MODEL_NAME,
        "train_task": TRAIN_TASK,
        "framework": "Unsloth + TRL GRPOTrainer",
        "train_time_minutes": round(train_time / 60, 1),
        "num_prompts": len(prompts),
        "num_epochs": NUM_EPOCHS,
        "lora_rank": LORA_RANK,
        "baseline": {k: {"avg": round(v["avg"], 2), "std": round(v["std"], 2)} for k, v in baseline_results.items()},
        "trained": {k: {"avg": round(v["avg"], 2) if v["avg"] is not None else None,
                        "std": round(v["std"], 2) if v["std"] is not None else None}
                    for k, v in trained_results.items()},
        "reward_start": round(float(np.mean([h['reward'] for h in log_history if 'reward' in h][:5])), 4) if log_history else None,
        "reward_end":   round(float(np.mean([h['reward'] for h in log_history if 'reward' in h][-20:])), 4) if log_history else None,
    }
    with open("training/outputs/summary_unsloth.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("  TRAINING COMPLETE (Unsloth)")
    print("=" * 60)
    print(f"  Time: {train_time/60:.1f} minutes")
    print(f"  {'Task':<20} {'Baseline':>10} {'Trained':>10} {'Δ':>8}")
    print(f"  {'-'*50}")
    for t in common_tasks:
        b, a = baseline_results[t]['avg'], trained_results[t]['avg']
        arrow = '↑' if a > b else '↓'
        print(f"  {t:<20} {b:>10.2f} {a:>10.2f} {arrow} {abs(a-b):.2f}")
    print("=" * 60)

    return summary


# ── Main ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        summary = run_grpo_training()
    except Exception as e:
        print(f"\nERROR during training: {e}")
        traceback.print_exc()
        os.makedirs("training/outputs", exist_ok=True)
        with open("training/outputs/summary_unsloth.json", "w") as f:
            json.dump({"error": str(e)}, f)

    if os.environ.get("OPENGRID_MODE") != "training":
        print("\nTraining done. Starting full UI server on port 7860...")
        import uvicorn
        from app import app
        uvicorn.run(app, host="0.0.0.0", port=7860)
    else:
        print("\nTraining done. UI server already running in background.")
