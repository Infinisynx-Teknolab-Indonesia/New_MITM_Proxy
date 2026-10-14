"""Kirim request+response ke AI lokal (Prakash AI) untuk dijelaskan.

Mendukung dua jenis endpoint:
- "openai": OpenAI-compatible /v1/chat/completions (llama.cpp server, LM Studio,
            vLLM, text-generation-webui, dll)
- "ollama": Ollama /api/chat

Hanya pakai pustaka standar (urllib), tidak perlu install apa-apa.
"""
import json
import re
import urllib.request

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _looks_binary(s):
    sample = s[:1000]
    if not sample:
        return False
    bad = sum(1 for c in sample if (ord(c) < 32 and c not in "\n\r\t") or ord(c) >= 127)
    return bad / len(sample) > 0.2


def _clean(s, limit=10000):
    """Buang karakter kontrol; kalau terlihat biner/terkompresi, ganti catatan."""
    if not s:
        return ""
    if _looks_binary(s):
        return (f"[body biner atau terkompresi ({len(s)} karakter) — tidak dikirim ke AI. "
                f"Kalau ini brotli/zstd, install: pip install brotli zstandard supaya terbaca.]")
    return _CTRL.sub("", s)[:limit]

SYSTEM = (
    "Kamu asisten keamanan web. Jelaskan dalam Bahasa Indonesia secara ringkas dan jelas: "
    "apa maksud request HTTP ini, apa yang dikembalikan response-nya, parameter/header penting, "
    "kemungkinan fungsinya, dan hal menarik dari sisi keamanan (auth, token, cookie, data sensitif). "
    "Jangan mengarang; kalau tidak yakin katakan tidak yakin."
)


def _parse_sse(raw):
    """Gabungkan jawaban dari balasan streaming (Server-Sent Events)."""
    parts = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        d = line[5:].strip()
        if d == "[DONE]" or not d:
            continue
        try:
            obj = json.loads(d)
        except json.JSONDecodeError:
            continue
        ch = (obj.get("choices") or [{}])[0]
        delta = ch.get("delta") or {}
        if delta.get("content"):
            parts.append(delta["content"])
        elif ch.get("message", {}).get("content"):
            parts.append(ch["message"]["content"])
        elif obj.get("message", {}).get("content"):   # ollama stream
            parts.append(obj["message"]["content"])
        elif obj.get("response"):                      # ollama generate stream
            parts.append(obj["response"])
    return "".join(parts)


def _post(url, payload, api_key=None, timeout=600):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # balasan streaming / SSE -> rakit jadi satu dict standar
        joined = _parse_sse(raw)
        return {"choices": [{"message": {"content": joined}}],
                "message": {"content": joined}}


def list_models(cfg, timeout=20):
    """Ambil daftar model dari gateway. Kembalikan list[str] (bisa kosong)."""
    url = (cfg.get("url") or "").strip()
    kind = cfg.get("kind", "openai")
    api_key = cfg.get("api_key") or ""
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        if kind == "ollama":
            base = url.split("/api/", 1)[0]
            req = urllib.request.Request(base + "/api/tags", headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        # openai-compatible: .../v1/chat/completions -> .../v1/models
        base = url.rsplit("/chat/completions", 1)[0]
        req = urllib.request.Request(base + "/models", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
    except Exception:
        return []


def _tidy(s):
    """Rapikan output Markdown AI jadi teks biasa yang enak dibaca di Tkinter."""
    if not s:
        return s
    out = []
    for ln in s.split("\n"):
        t = ln.rstrip()
        st = t.strip()
        # garis pemisah (--- *** ___)
        if len(st) >= 3 and set(st) <= set("-*_ ") and st.strip("-*_ ") == "":
            continue
        # heading (#, ##, ###) -> teks kapital
        m = re.match(r"^\s*#{1,6}\s*(.*)$", t)
        if m:
            h = m.group(1).strip()
            if h:
                out.append(h.upper())
            continue
        # bullet (* - +) -> •
        m = re.match(r"^(\s*)[\*\-\+]\s+(.*)$", t)
        if m:
            t = m.group(1) + "• " + m.group(2)
        out.append(t)
    text = "\n".join(out)
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def context_text(req_text, res_text):
    """Gabungan request+response (sudah dibersihkan) untuk konteks ke AI."""
    return ("=== REQUEST ===\n" + _clean(req_text, 4000) +
            "\n\n=== RESPONSE ===\n" + _clean(res_text, 4000))


def chat(messages, cfg, tidy=True):
    """Kirim daftar messages (role/content) ke AI, kembalikan jawaban (str)."""
    url = (cfg.get("url") or "").strip()
    if not url:
        raise ValueError("URL AI belum diisi di Settings > AI.")
    model = (cfg.get("model") or "").strip()
    kind = cfg.get("kind", "openai")
    api_key = cfg.get("api_key") or ""
    fix = _tidy if tidy else (lambda x: x)
    if kind == "ollama":
        payload = {"model": model or "llama3", "messages": messages, "stream": False,
                   "options": {"num_predict": 1200}}
        out = _post(url, payload, api_key)
        return fix((out.get("message") or {}).get("content", "").strip()) or json.dumps(out)[:2000]
    payload = {"model": model or "local-model", "messages": messages,
               "stream": False, "temperature": 0.2, "max_tokens": 1200}
    out = _post(url, payload, api_key)
    try:
        return fix(out["choices"][0]["message"]["content"].strip())
    except (KeyError, IndexError):
        return json.dumps(out)[:2000]


PLAN_SYSTEM = (
    "Kamu membuat daftar HTTP request untuk dijalankan otomatis oleh sebuah tool. "
    "Jawab HANYA dengan array JSON valid, tanpa penjelasan, tanpa markdown. "
    "Tiap elemen: {\"method\":\"GET\",\"url\":\"https://host/path\",\"headers\":{\"K\":\"V\"},\"body\":\"\"}. "
    "headers dan body opsional. Maksimum 30 request. Jangan menamb—hanya array JSON."
)


def plan_requests(instruction, base_text, cfg):
    """Minta AI menyusun daftar request. Kembalikan list[dict]."""
    user = instruction.strip()
    if base_text and base_text.strip():
        user += "\n\nContoh request dasar (boleh dijadikan acuan):\n" + _clean(base_text, 3000)
    messages = [{"role": "system", "content": PLAN_SYSTEM},
                {"role": "user", "content": user}]
    raw = chat(messages, cfg, tidy=False)
    # ambil blok array JSON pertama
    i, j = raw.find("["), raw.rfind("]")
    if i < 0 or j < 0 or j <= i:
        raise ValueError("AI tidak mengembalikan array JSON.\n\n" + raw[:1500])
    arr = json.loads(raw[i:j + 1])
    out = []
    for item in arr:
        if isinstance(item, dict) and item.get("url"):
            out.append({
                "method": (item.get("method") or "GET").upper(),
                "url": item["url"],
                "headers": item.get("headers") or {},
                "body": item.get("body") or "",
            })
    if not out:
        raise ValueError("Array JSON kosong / tidak ada 'url'.")
    return out


def explain(req_text, res_text, cfg):
    """Kembalikan penjelasan (str). Lempar Exception kalau gagal."""
    url = (cfg.get("url") or "").strip()
    if not url:
        raise ValueError("URL AI belum diisi di Settings > AI.")
    model = (cfg.get("model") or "").strip()
    kind = cfg.get("kind", "openai")
    api_key = cfg.get("api_key") or ""

    user = (
        "Jelaskan request & response HTTP berikut.\n\n"
        "=== REQUEST ===\n" + _clean(req_text, 4000) +
        "\n\n=== RESPONSE ===\n" + _clean(res_text, 4000)
    )
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": user}]

    if kind == "ollama":
        payload = {"model": model or "llama3", "messages": messages, "stream": False,
                   "options": {"num_predict": 700}}
        out = _post(url, payload, api_key)
        return _tidy((out.get("message") or {}).get("content", "").strip()) or json.dumps(out)[:2000]

    # default: OpenAI-compatible
    payload = {"model": model or "local-model", "messages": messages,
               "stream": False, "temperature": 0.2, "max_tokens": 700}
    out = _post(url, payload, api_key)
    try:
        return _tidy(out["choices"][0]["message"]["content"].strip())
    except (KeyError, IndexError):
        return json.dumps(out)[:2000]
