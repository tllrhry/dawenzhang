"""Live probes for the SiliconFlow embedding/rerank and DeepSeek chat APIs.

Verifies model identifiers, response structure, embedding dimension, batch
handling and per-call timeouts against the real endpoints using the configured
credentials. Run manually (it makes network calls and is NOT part of the test
gate):

    PYTHONPATH=backend python backend/scripts/probe_models.py

Exit code 0 means every probe passed; non-zero means at least one failed.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

import httpx

from app.core.config import get_settings


@dataclass
class ProbeResult:
    name: str
    ok: bool
    detail: str
    elapsed: float


def _timeout(connect: float, read: float) -> httpx.Timeout:
    return httpx.Timeout(read, connect=connect)


def probe_embedding(settings) -> ProbeResult:
    name = "siliconflow.embedding"
    inputs = ["软件开发与信息技术服务", "稻谷种植与农业生产", "商业银行货币金融服务"]
    started = time.perf_counter()
    try:
        response = httpx.post(
            f"{settings.siliconflow_base_url}/embeddings",
            headers={"Authorization": f"Bearer {settings.siliconflow_api_key}"},
            json={"model": settings.siliconflow_embedding_model, "input": inputs},
            timeout=_timeout(settings.http_connect_timeout_seconds, settings.siliconflow_timeout_seconds),
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - probe surfaces any failure
        return ProbeResult(name, False, f"request failed: {exc}", time.perf_counter() - started)

    elapsed = time.perf_counter() - started
    data = payload.get("data") or []
    if len(data) != len(inputs):
        return ProbeResult(name, False, f"expected {len(inputs)} vectors, got {len(data)}", elapsed)
    dims = {len(item.get("embedding") or []) for item in data}
    if dims != {settings.embedding_dimension}:
        return ProbeResult(
            name,
            False,
            f"dimension mismatch: got {dims}, EMBEDDING_DIMENSION={settings.embedding_dimension}",
            elapsed,
        )
    return ProbeResult(
        name,
        True,
        f"model={payload.get('model')} batch={len(data)} dim={settings.embedding_dimension}",
        elapsed,
    )


def probe_rerank(settings) -> ProbeResult:
    name = "siliconflow.rerank"
    documents = ["软件和信息技术服务业", "稻谷种植", "货币银行服务", "汽车制造"]
    started = time.perf_counter()
    try:
        response = httpx.post(
            f"{settings.siliconflow_base_url}/rerank",
            headers={"Authorization": f"Bearer {settings.siliconflow_api_key}"},
            json={
                "model": settings.siliconflow_rerank_model,
                "query": "从事计算机软件开发的科技公司",
                "documents": documents,
                "top_n": 3,
            },
            timeout=_timeout(settings.http_connect_timeout_seconds, settings.siliconflow_timeout_seconds),
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(name, False, f"request failed: {exc}", time.perf_counter() - started)

    elapsed = time.perf_counter() - started
    results = payload.get("results") or []
    if not results:
        return ProbeResult(name, False, "empty results", elapsed)
    for item in results:
        if "index" not in item or "relevance_score" not in item:
            return ProbeResult(name, False, f"unexpected result shape: {item}", elapsed)
        if not 0 <= item["index"] < len(documents):
            return ProbeResult(name, False, f"index out of range: {item['index']}", elapsed)
    top = results[0]
    return ProbeResult(
        name,
        True,
        f"model={settings.siliconflow_rerank_model} top_index={top['index']} score={top['relevance_score']:.4f}",
        elapsed,
    )


def probe_deepseek(settings) -> ProbeResult:
    name = "deepseek.chat"
    started = time.perf_counter()
    try:
        response = httpx.post(
            f"{settings.deepseek_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={
                "model": settings.deepseek_model,
                "messages": [
                    {"role": "system", "content": "只输出 JSON。"},
                    {"role": "user", "content": '返回 {"ok": true}'},
                ],
                "temperature": 0,
                "max_tokens": 50,
                "response_format": {"type": "json_object"},
            },
            timeout=_timeout(settings.http_connect_timeout_seconds, settings.deepseek_timeout_seconds),
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(name, False, f"request failed: {exc}", time.perf_counter() - started)

    elapsed = time.perf_counter() - started
    choices = payload.get("choices") or []
    if not choices:
        return ProbeResult(name, False, "empty choices", elapsed)
    content = (choices[0].get("message") or {}).get("content")
    if not content:
        return ProbeResult(name, False, "empty content", elapsed)
    return ProbeResult(
        name,
        True,
        f"model={payload.get('model')} content={content.strip()[:60]}",
        elapsed,
    )


def main() -> int:
    settings = get_settings()
    missing = []
    if not settings.siliconflow_api_key:
        missing.append("SILICONFLOW_API_KEY")
    if not settings.deepseek_api_key:
        missing.append("DEEPSEEK_API_KEY")
    if missing:
        print(f"[FAIL] missing required config: {', '.join(missing)}", file=sys.stderr)
        return 2

    probes = [probe_embedding, probe_rerank, probe_deepseek]
    all_ok = True
    for probe in probes:
        result = probe(settings)
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.name} ({result.elapsed:.2f}s) - {result.detail}")
        all_ok = all_ok and result.ok
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
