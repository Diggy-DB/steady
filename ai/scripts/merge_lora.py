"""Add a trained LoRA adapter (scripts/train_lora.py) into a full copy of the model, for vLLM to serve.

vLLM can't load adapters for Qwen3.5's linear-attention layers, so the fine-tuned model is served as
a whole model. This writes the original checkpoint again with only the trained weights changed:

    W_new = W + (lora_alpha / r) * B @ A          (computed in float32, stored in the original type)

Everything else is copied as it is: the picture reader (model.visual...), the extra next-token head
(mtp...), the config, tokenizer, chat template and image-processor files. So the result answers
pictures like the original and loads with the same `vllm serve` flags.

Training used the text part alone, where layers are named "model.layers.N..."; in the full checkpoint
they're "model.language_model.layers.N...". Every adapter matrix must land on exactly one weight, or
this stops without writing anything half-done.

    uv run --with torch scripts/merge_lora.py --adapter out/lora --out out/merged
    uv run --with torch scripts/merge_lora.py --base Qwen/Qwen3.5-4B --adapter out/lora --out out/merged
"""

import argparse
import json
import re
import shutil
from pathlib import Path

BASE_MODEL = "Qwen/Qwen3.5-4B"
LORA_KEY = re.compile(r"^base_model\.model\.(?P<module>.+)\.lora_(?P<part>[AB])(?:\.default)?\.weight$")


def base_folder(base: str) -> Path:
    """The model's files on disk: a folder as given, or the Hugging Face download (fetched if missing)."""
    if Path(base).is_dir():
        return Path(base)
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(base))


def checkpoint_key(module: str, keys: set[str]) -> str:
    """The checkpoint weight a trained module belongs to, e.g. "model.layers.3.mlp.up_proj" ->
    "model.language_model.layers.3.mlp.up_proj.weight"."""
    candidates = [f"{module}.weight"]
    if module.startswith("model."):
        candidates.append("model.language_model." + module.removeprefix("model.") + ".weight")
    found = [c for c in candidates if c in keys]
    if len(found) != 1:
        raise SystemExit(f"Can't place the adapter's {module}: looked for {candidates}, found {found}")
    return found[0]


def load_adapter(folder: Path) -> tuple[dict, float]:
    """The adapter's matrices by module, {module: {"A": tensor, "B": tensor}}, and its scale."""
    from safetensors.torch import load_file

    config = json.loads((folder / "adapter_config.json").read_text())
    if config.get("use_dora") or config.get("fan_in_fan_out"):
        raise SystemExit("This merge handles plain LoRA only (no DoRA, no fan_in_fan_out).")
    rank, alpha = config["r"], config["lora_alpha"]
    scale = alpha / rank ** 0.5 if config.get("use_rslora") else alpha / rank
    pairs: dict[str, dict] = {}
    for key, tensor in load_file(folder / "adapter_model.safetensors").items():
        match = LORA_KEY.match(key)
        if not match:
            raise SystemExit(f"Unexpected weight in the adapter: {key}")
        pairs.setdefault(match["module"], {})[match["part"]] = tensor
    incomplete = [m for m, p in pairs.items() if set(p) != {"A", "B"}]
    if incomplete:
        raise SystemExit(f"Adapter matrices without their pair: {incomplete[:3]}")
    return pairs, scale


def merge(base: Path, adapter: Path, out: Path) -> dict:
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file

    pairs, scale = load_adapter(adapter)
    index_file = base / "model.safetensors.index.json"
    if index_file.exists():
        weight_map = json.loads(index_file.read_text())["weight_map"]
    else:
        with safe_open(base / "model.safetensors", "pt") as f:
            weight_map = {k: "model.safetensors" for k in f.keys()}
    targets = {checkpoint_key(module, set(weight_map)): module for module in pairs}

    tmp = out.with_name(out.name + ".partial")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for item in base.iterdir():  # config, tokenizer, chat template, image processor, the index...
        if not item.name.endswith(".safetensors") and item.is_file():
            shutil.copy(item, tmp / item.name)

    changed, largest = 0, 0.0
    for shard in sorted(set(weight_map.values())):
        tensors = {}
        with safe_open(base / shard, "pt") as f:
            metadata = f.metadata() or {"format": "pt"}
            for key in f.keys():
                weight = f.get_tensor(key)
                if key in targets:
                    lora = pairs[targets[key]]
                    delta = scale * (lora["B"].float() @ lora["A"].float())
                    if delta.shape != weight.shape:
                        raise SystemExit(f"{key}: weight {tuple(weight.shape)} but adapter change {tuple(delta.shape)}")
                    weight = (weight.float() + delta).to(weight.dtype)
                    changed += 1
                    largest = max(largest, delta.abs().max().item())
                tensors[key] = weight.contiguous()
        save_file(tensors, tmp / shard, metadata=metadata)
        print(f"wrote {shard} ({len(tensors)} weights)", flush=True)
    if changed != len(targets):
        raise SystemExit(f"Changed {changed} weights but the adapter has {len(targets)} modules")

    summary = {"base": str(base), "adapter": str(adapter), "scale": scale, "changed_weights": changed,
               "largest_change": largest}
    adapter_summary = adapter / "train_summary.json"
    if adapter_summary.exists():
        summary["training"] = {k: v for k, v in json.loads(adapter_summary.read_text()).items() if k != "loss_per_update"}
    (tmp / "steady_merge.json").write_text(json.dumps(summary, indent=2))
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a LoRA adapter into a full copy of the model.")
    parser.add_argument("--base", default=BASE_MODEL, help="the original model (a Hugging Face name or a folder)")
    parser.add_argument("--adapter", required=True, help="the folder train_lora.py saved")
    parser.add_argument("--out", required=True, help="where to write the merged model")
    args = parser.parse_args()
    summary = merge(base_folder(args.base), Path(args.adapter), Path(args.out))
    print(f"Merged {summary['changed_weights']} weights (scale {summary['scale']:g}, largest change "
          f"{summary['largest_change']:.4f}) into {args.out}")


if __name__ == "__main__":
    main()
