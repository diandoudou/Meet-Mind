"""Chinese-CLIP (中文 CLIP) embeddings for multimodal image_vector channel."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional


def _model_id() -> str:
    return os.getenv(
        "CHINESE_CLIP_MODEL",
        "OFA-Sys/chinese-clip-vit-base-patch16",
    )


def _device() -> str:
    forced = os.getenv("CHINESE_CLIP_DEVICE", "").strip()
    if forced:
        return forced
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


@lru_cache(maxsize=1)
def _load_model():
    """Lazy-load transformers ChineseCLIP. Returns (model, processor, device) or None."""
    try:
        import torch
        from transformers import ChineseCLIPModel, ChineseCLIPProcessor
    except Exception as exc:
        print(f"[RAG] Chinese-CLIP unavailable (install transformers+torch): {exc}")
        return None

    model_id = _model_id()
    device = _device()
    try:
        processor = ChineseCLIPProcessor.from_pretrained(model_id)
        model = ChineseCLIPModel.from_pretrained(model_id)
        model.eval()
        model.to(device)
        print(f"[RAG] Loaded Chinese-CLIP '{model_id}' on {device}")
        return model, processor, device, torch
    except Exception as exc:
        print(f"[RAG] Chinese-CLIP load failed: {exc}")
        return None


def chinese_clip_dim() -> int:
    bundled = _load_model()
    if bundled is None:
        return int(os.getenv("CHINESE_CLIP_DIM", "512"))
    model, processor, device, torch = bundled
    with torch.no_grad():
        inputs = processor(text=["dim probe"], padding=True, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        feats = model.get_text_features(**inputs)
        return int(feats.shape[-1])


def embed_texts_chinese_clip(texts: List[str]) -> List[List[float]]:
    """Encode query/caption text into Chinese-CLIP space (L2-normalized)."""
    if not texts:
        return []
    bundled = _load_model()
    if bundled is None:
        # Fallback: zero vectors of expected dim (caller may skip image channel)
        dim = chinese_clip_dim()
        return [[0.0] * dim for _ in texts]

    model, processor, device, torch = bundled
    out: List[List[float]] = []
    batch_size = int(os.getenv("CHINESE_CLIP_BATCH", "8"))
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            batch = [t[:200] if t else " " for t in texts[i : i + batch_size]]
            inputs = processor(text=batch, padding=True, return_tensors="pt", truncation=True)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            feats = model.get_text_features(**inputs)
            feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
            out.extend(feats.cpu().tolist())
    return out


def embed_images_chinese_clip(image_paths: List[Optional[str]]) -> List[List[float]]:
    """
    Encode images into Chinese-CLIP space.
    Missing/unreadable paths yield a zero vector (same dim).
    """
    if not image_paths:
        return []
    bundled = _load_model()
    dim = chinese_clip_dim()
    if bundled is None:
        return [[0.0] * dim for _ in image_paths]

    model, processor, device, torch = bundled
    try:
        from PIL import Image
    except Exception:
        return [[0.0] * dim for _ in image_paths]

    vectors: List[List[float]] = []
    with torch.no_grad():
        for path in image_paths:
            if not path or not Path(path).exists():
                vectors.append([0.0] * dim)
                continue
            try:
                image = Image.open(path).convert("RGB")
                inputs = processor(images=image, return_tensors="pt")
                inputs = {k: v.to(device) for k, v in inputs.items()}
                feats = model.get_image_features(**inputs)
                feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
                vectors.append(feats[0].cpu().tolist())
            except Exception as exc:
                print(f"[RAG] Chinese-CLIP image encode failed for {path}: {exc}")
                vectors.append([0.0] * dim)
    return vectors


def build_image_vectors_for_chunks(
    modalities: List[str],
    image_paths: List[str],
    captions: List[str],
    texts: List[str],
) -> List[List[float]]:
    """
    Per-chunk Chinese-CLIP vectors:
    - image modality with path → encode image
    - else → encode caption/text (so text queries can still hit via CLIP space)
    """
    n = len(modalities)
    paths: List[Optional[str]] = []
    text_fallback_idx: List[int] = []
    text_fallback: List[str] = []

    for i in range(n):
        if modalities[i] == "image" and image_paths[i]:
            paths.append(image_paths[i])
        else:
            paths.append(None)
            text_fallback_idx.append(i)
            text_fallback.append((captions[i] or texts[i] or " ")[:200])

    vectors = embed_images_chinese_clip(paths)
    if text_fallback:
        text_vecs = embed_texts_chinese_clip(text_fallback)
        for j, idx in enumerate(text_fallback_idx):
            vectors[idx] = text_vecs[j]
    return vectors
