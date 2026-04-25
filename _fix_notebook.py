"""Update the notebook: fix rewards, hyperparams, remove emojis, show plots inline."""
import json

nb = json.load(open('training/opengrid_grpo_colab.ipynb', encoding='utf-8'))

# Remove emojis from all cells
for cell in nb['cells']:
    for i, line in enumerate(cell.get('source', [])):
        for emoji in ['🔋','⚡','🚀','📊','✅','⚠️']:
            line = line.replace(emoji, '')
        cell['source'][i] = line

# Fix Cell 8: use compute_grpo_reward_env
for cell in nb['cells']:
    src = ''.join(cell.get('source', []))
    if 'compute_grpo_reward,' in src and 'def reward_fn' in src:
        cell['source'] = [
            'import json as _json\n',
            'from training.train_grpo import compute_grpo_reward_env, extract_action\n',
            '\n',
            'def reward_fn(completions, obs_context=None, **kwargs):\n',
            '    """GRPO reward function with env-grounded physics rewards."""\n',
            '    texts = []\n',
            '    for c in completions:\n',
            '        if isinstance(c, list):\n',
            '            text = c[-1]["content"] if c else ""\n',
            '        else:\n',
            '            text = str(c)\n',
            '        texts.append(text)\n',
            '\n',
            '    if obs_context is None:\n',
            '        batch_obs = [None] * len(texts)\n',
            '    else:\n',
            '        batch_obs = [\n',
            '            _json.loads(ctx) if isinstance(ctx, str) else ctx\n',
            '            for ctx in obs_context\n',
            '        ]\n',
            '    return compute_grpo_reward_env(texts, batch_obs, task_config, horizon=3)\n',
            '\n',
            '# Sanity test\n',
            'test_rewards = reward_fn([\n',
            '    \'{"bus_adjustments": [{"bus_id": 1, "delta": 5.0}], "topology_actions": []}\',\n',
            '    "invalid json here",\n',
            '])\n',
            'print(f"Test rewards: {test_rewards}")\n',
            'assert len(test_rewards) == 2\n',
            'print("[OK] reward_fn works")\n',
        ]
        break

# Fix Cell 9: update hyperparameters
for cell in nb['cells']:
    src = ''.join(cell.get('source', []))
    if 'GRPOConfig(' in src and 'num_generations' in src:
        new_src = src.replace('num_train_epochs=1', 'num_train_epochs=3')
        new_src = new_src.replace('gradient_accumulation_steps=4', 'gradient_accumulation_steps=8')
        new_src = new_src.replace('learning_rate=5e-6', 'learning_rate=1e-5')
        new_src = new_src.replace('num_generations=4', 'num_generations=8')
        cell['source'] = new_src.splitlines(True)
        break

# Fix download cell: replace google.colab with inline display
for cell in nb['cells']:
    src = ''.join(cell.get('source', []))
    if 'google.colab' in src:
        cell['source'] = [
            '# Display plots inline\n',
            'from IPython.display import Image, display\n',
            'display(Image("training/outputs/before_after.png"))\n',
            'display(Image("training/outputs/training_loss.png"))\n',
        ]
        break

json.dump(nb, open('training/opengrid_grpo_colab.ipynb', 'w', encoding='utf-8'), indent=1)
print("Notebook updated successfully")
