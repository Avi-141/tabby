"""LLM summarization and embedding functions for Ollama and GGUF backends."""

import os
import sys
from typing import List, Optional

import requests


def build_prompt(title: str, text: str) -> str:
    """Build a summarization prompt for the LLM."""
    return (
        "Summarize the page in 2-3 sentences. Focus on what it is about and why it matters.\n"
        f"Title: {title or 'Untitled'}\n"
        f"Content:\n{text}\n\n"
        "Summary:"
    )


def build_embedding_text(title: str, summary: str, domain: str, fallback: str) -> str:
    """Build text for embedding generation."""
    parts = []
    if title:
        parts.append(f"Title: {title}")
    if summary:
        parts.append(f"Summary: {summary}")
    if domain:
        parts.append(f"Domain: {domain}")
    if not parts and fallback:
        parts.append(fallback)
    return "\n".join(parts)


def summarize_ollama(prompt: str, model: str, base_url: str, timeout: int) -> str:
    """Generate summary using Ollama API."""
    url = base_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 200},
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return (data.get("response") or "").strip()


def embed_ollama(
    text: str, model: str, base_url: str, timeout: int
) -> Optional[List[float]]:
    """Generate embedding using Ollama API."""
    url = base_url.rstrip("/") + "/api/embeddings"
    payload = {"model": model, "prompt": text}
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if "embedding" in data:
        return data.get("embedding")
    if "data" in data and data["data"]:
        return data["data"][0].get("embedding")
    return None


def build_llama(model_path: str, n_ctx: int, n_threads: int, n_gpu_layers: int):
    """Build a llama-cpp-python model instance."""
    try:
        from llama_cpp import Llama
    except ImportError:
        print(
            "[ERROR] Missing dependency: llama-cpp-python. Install with: pip install llama-cpp-python",
            file=sys.stderr,
        )
        raise
    return Llama(
        model_path=model_path,
        n_ctx=n_ctx,
        n_threads=n_threads,
        n_gpu_layers=n_gpu_layers,
    )


def summarize_llama(llm, prompt: str) -> str:
    """Generate summary using llama-cpp-python."""
    out = llm(prompt, max_tokens=220, temperature=0.2, stop=["\n\n", "Summary:"])
    return (out.get("choices") or [{}])[0].get("text", "").strip()
