"""OpenGrid GRPO Training Runner for HF Spaces.

Runs env-grounded GRPO training, saves model + plots,
then starts a FastAPI server to serve/download results.
"""
import os
import sys
import json
import copy
import time
import shutil
import traceback
from pathlib import Path

# ── Training ──────────────────────────────────────────────────────
def run_grpo_training():
    """Run GRPO training with env-grounded rewards."""
    import torch
    import numpy as np

    print("=" * 60)
    print("  OpenGrid GRPO Training")
    print("=" * 60)

    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    else:
        print("WARNING: No GPU detected — training will be very slow!")

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

    # ── 1. Load model ──
    print("\n[1/6] Loading model with Unsloth...")
    try:
        from unsloth import FastLanguageModel
        MODEL_NAME = "unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit"
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=MODEL_NAME, max_seq_length=2048, load_in_4bit=True,
        )
        model = FastLanguageModel.get_peft_model(
            model, r=16, lora_alpha=16, lora_dropout=0,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"],
        )
        print(f"  Model: {MODEL_NAME}")
        print(f"  Trainable params: {sum(p.numel() for p in model.parameters() if p.requires_grad):,}")
    except ImportError:
        print("WARNING: Unsloth not available, using standard loading")
        from transformers import AutoTokenizer, AutoModelForCausalLM
        MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

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
    for task_id in ["task_easy", "task_medium", "task_karnataka"]:
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

    for episode in range(30):
        ep_config = copy.deepcopy(task_config)
        ep_config['seed'] = base_seed + episode
        env = OpenGridEnv(ep_config)
        zone_obs = env.reset_multi()

        # Adversarial: drain batteries every 5th episode
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

    _bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    _fp16 = torch.cuda.is_available() and not _bf16

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

        return compute_grpo_reward_env(texts, obs_dicts, task_config, horizon=3)

    grpo_config = GRPOConfig(
        output_dir="training/outputs/grpo_checkpoints",
        num_train_epochs=3,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=1e-5,
        logging_steps=5,
        save_steps=50,
        max_completion_length=256,
        num_generations=8,
        report_to="none",
        remove_unused_columns=False,
        bf16=_bf16,
        fp16=_fp16,
    )

    train_dataset = Dataset.from_dict({"prompt": prompts, "obs_context": obs_contexts})
    print(f"  Dataset: {len(train_dataset)} rows")
    print(f"  Effective batch: {grpo_config.per_device_train_batch_size * grpo_config.gradient_accumulation_steps}")

    trainer = GRPOTrainer(
        model=model, args=grpo_config, train_dataset=train_dataset,
        reward_funcs=reward_fn, processing_class=tokenizer,
    )

    t0 = time.time()
    trainer.train()
    train_time = time.time() - t0
    print(f"\n  Training complete in {train_time/60:.1f} minutes")

    # Save model
    output_path = "training/outputs/trained_model"
    trainer.save_model(output_path)
    tokenizer.save_pretrained(output_path)
    print(f"  Model saved to {output_path}")

    # ── 5. Post-training evaluation ──
    print("\n[5/6] Evaluating trained model...")
    try:
        FastLanguageModel.for_inference(model)
    except Exception:
        pass

    def trained_generate(prompt):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        formatted = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(formatted, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=256, temperature=0.3, do_sample=True)
        return tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)

    trained_results = {}
    for task_id in ["task_easy", "task_medium", "task_karnataka"]:
        if task_id not in TASKS:
            continue
        config = TASKS[task_id]
        rewards = []
        for ep in range(3):
            ep_config = copy.deepcopy(config)
            ep_config['seed'] = 42 + ep
            env = OpenGridEnv(ep_config)
            result = rollout_multi_agent(env, trained_generate, ep_config)
            rewards.append(result['total_reward'])
            print(f"    {task_id} ep{ep}: reward={result['total_reward']:.2f}")
        trained_results[task_id] = {"avg": np.mean(rewards), "std": np.std(rewards), "rewards": rewards}
        print(f"  [TRAINED] {task_id}: {np.mean(rewards):.2f} ± {np.std(rewards):.2f}")

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
        ax.bar(x + width/2, after, width, label='GRPO Trained', color='#00d4aa', alpha=0.8)
        ax.set_xlabel('Task'); ax.set_ylabel('Average Episode Reward')
        ax.set_title('OpenGrid — GRPO Training: Before vs After', fontweight='bold')
        ax.set_xticks(x); ax.set_xticklabels([t.replace('task_', '').title() for t in common_tasks])
        ax.legend(); ax.grid(True, alpha=0.3, axis='y')
        for bars in ax.containers:
            for bar in bars:
                h = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., h + (1 if h >= 0 else -3),
                        f'{h:.1f}', ha='center', va='bottom' if h >= 0 else 'top', fontsize=10)
        plt.tight_layout()
        plt.savefig('training/outputs/before_after.png', dpi=150)
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
        ax.set_title('OpenGrid GRPO — Training Loss', fontweight='bold')
        ax.legend(); ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig('training/outputs/training_loss.png', dpi=150)
        plt.close()

    # Save summary
    summary = {
        "model": MODEL_NAME,
        "train_task": TRAIN_TASK,
        "train_time_minutes": round(train_time / 60, 1),
        "num_prompts": len(prompts),
        "num_epochs": 3,
        "baseline": {k: {"avg": round(v["avg"], 2), "std": round(v["std"], 2)} for k, v in baseline_results.items()},
        "trained": {k: {"avg": round(v["avg"], 2), "std": round(v["std"], 2)} for k, v in trained_results.items()},
    }
    with open("training/outputs/summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("  TRAINING COMPLETE")
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


# ── Results Server ────────────────────────────────────────────────
def serve_results():
    """Serve training results on port 7860."""
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, JSONResponse
    import uvicorn

    app = FastAPI(title="OpenGrid Training Results")

    @app.get("/")
    def root():
        summary_path = Path("training/outputs/summary.json")
        if summary_path.exists():
            with open(summary_path) as f:
                return json.load(f)
        return {"status": "Training in progress or no results yet"}

    @app.get("/plots/before_after")
    def before_after():
        p = Path("training/outputs/before_after.png")
        if p.exists():
            return FileResponse(str(p), media_type="image/png")
        return JSONResponse({"error": "not ready"}, status_code=404)

    @app.get("/plots/loss")
    def loss():
        p = Path("training/outputs/training_loss.png")
        if p.exists():
            return FileResponse(str(p), media_type="image/png")
        return JSONResponse({"error": "not ready"}, status_code=404)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    uvicorn.run(app, host="0.0.0.0", port=7860)


# ── Main ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        summary = run_grpo_training()
    except Exception as e:
        print(f"\nERROR during training: {e}")
        traceback.print_exc()
        # Save error so the results server can report it
        os.makedirs("training/outputs", exist_ok=True)
        with open("training/outputs/summary.json", "w") as f:
            json.dump({"error": str(e)}, f)

    print("\nStarting results server on port 7860...")
    serve_results()
