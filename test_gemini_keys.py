"""
Comprehensive Gemini API Key Tester v2
Tests each key against ALL available models to detect validity, rate-limits, shadowbans, bans.
"""
import asyncio
import time
import json
import sys
import aiohttp
from typing import Optional

# 40 Gemini API keys
GEMINI_KEYS = [
    "AIzaSyBFbY-3a4KPgvI9bsSfQ7urgG2hSv7HDM0",
    "AIzaSyDgeY0Uy-e-55TiBhLCRbgIzPJ9oGKgpl8",
    "AIzaSyC79QxcQBal_g9K3g7G0d6cy_VYJtmoArg",
    "AIzaSyCWZxS27wHPVeDrxHIl3Kwa7sxDUZ4bjmY",
    "AIzaSyBSJi9vU-S-FKnpx4PX7SUkLtyJT9UzyDI",
    "AIzaSyBJ6bj5--_tBO6fnGaIi9s6xrPp4OqLZ9Y",
    "AIzaSyAOqCOaj6hspmbrFm28eC45neC6LHFyqx0",
    "AIzaSyDuhVcT43sxynCqc0JcnOt8ghQ7iq5SbJo",
    "AIzaSyD3dNxlNRMizDxunTCOu3GkMR3ajq9dq28",
    "AIzaSyADxqrrSmShByiSXZYP6iJvzK2sosJhX5c",
    "AIzaSyCU6ag2TGqQ3NaLRWsqMaSLTa_jGsBv9fo",
    "AIzaSyBV50t36PQNqPBy7Vnv7FyfIZw_J1z41Ws",
    "AIzaSyC5b5EzbV3qMWT8RB7emxian1njyckvWbQ",
    "AIzaSyBe9M-KY8N2wJ8R0CspmHqWxrE0FV2FSnc",
    "AIzaSyAvwKpXEhX8ml670tj5XDDG75Aim6Socuw",
    "AIzaSyCXmNT_rlGaJ46w1Tqakbqi3rYcWnuyXXM",
    "AIzaSyB9sgjw-gI3eElIjN3Vs2iTSmhfF7w_wcE",
    "AIzaSyDAKk7b_iJVAsoQV4aNv5QAOicrW6bm2PU",
    "AIzaSyC2VN1nU4RTB6NGpUUoDvZ1BG36uAiXt0A",
    "AIzaSyCLS2s9u3PRfMT85Fl9oKIfHp2M4_QFgIo",
    "AIzaSyCc9eUkDKkjieboi2W-7xVXyiITKD_e0Qs",
    "AIzaSyCutj31DFdnrTAllubwlY2FdpNXZZrFqBQ",
    "AIzaSyDoju2sv99sFzOI6v0zfvC6kL0EyqE_MHo",
    "AIzaSyBnay1JboMO2faE5KEahRseEppxahvq0bE",
    "AIzaSyB5Kuvk0MZJspBlUb0valYCz1qiQy5dPzk",
    "AIzaSyBgAqEtMjKHCLHKLODQwhipyWn4l-poHJc",
    "AIzaSyDR80rYYnH6b30fS17tE-63_5vFcI6NF1w",
    "AIzaSyAHF3Sve3-vK2ecRX0SonUZdpWM5Vb3Jf8",
    "AIzaSyD5LyJEn6Qt0nQsCImAkyJnd8nCIuQLk20",
    "AIzaSyDsLEnLtkiQCXabNpUDhw7e6wXI0lpx7_k",
    "AIzaSyDsgeiIBlJT4CL6j9Bejcj9Wpx3S53dNxo",
    "AIzaSyB3JD-Aayqmd4m6FIdniOvqDEw9jt8yNFA",
    "AIzaSyAvTFb2E4TOlPTZjhKrUSNm4DW3ebtDN8M",
    "AIzaSyCykAV-jhIktKdhzq8TAgty6wXGAlECXsE",
    "AIzaSyDA2zNTjO3GHub2y44RfWe7a6JwwMJNSBc",
    "AIzaSyD_fE1Cua2oEL1Roi_M2AnUGxewkjO9XDA",
    "AIzaSyAhrQwyMlQYgPy89V4IQ0GCnPwcvz-9hHg",
    "AIzaSyDWEFPmdHzkqzEY3hbvfi27Hx8KWtTCKIQ",
    "AIzaSyCmGtxuzRPqXvkRwWgwemA9E1uCftcqxmk",
    "AIzaSyCocaQ_GkS1tEEpe7VwQo2u4qSuhhu7NaQ",
]

# ALL text-out models from the user's quota list (model IDs for the API)
# These are the generateContent-capable models
ALL_MODELS = [
    # Gemini 2.5 Flash variant models
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash-preview-05-20-2025",
    "gemini-2.5-pro",
    # Gemini 2.0 Flash variants
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-001",
    # Gemini 1.5 Flash (broadly available)
    "gemini-1.5-flash",
    "gemini-1.5-flash-002",
    # Gemini 3 Flash / Lite / Pro (newer models)
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.1-pro-preview",
    # Gemma 3 models
    "gemma-3-27b-it",
    "gemma-3-12b-it",
    "gemma-3-4b-it",
    "gemma-3-1b-it",
    # Gemma 4 models
    "gemma-4-26b-a4b-it",
    "gemma-4-31b-it",
]

TEST_PROMPT = "Reply with exactly one word: OK"
TIMEOUT = 25  # seconds
CONCURRENT = 5

STATUS_ICONS = {
    "OK": "+",
    "RATE_LIMITED": "R",
    "SHADOWBANNED": "S",
    "BANNED": "X",
    "INVALID_KEY": "X",
    "MODEL_NOT_FOUND": "-",
    "SERVER_ERROR": "E",
    "TIMEOUT": "T",
    "UNAVAILABLE": "U",
    "ERROR": "?",
}


async def test_key_model(session: aiohttp.ClientSession, key: str, model_id: str, sem: asyncio.Semaphore) -> dict:
    """Test a single key+model combination via REST API."""
    async with sem:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": TEST_PROMPT}]}],
            "generationConfig": {"maxOutputTokens": 20},
        }
        result = {"model": model_id, "status": "UNKNOWN", "error": "", "latency_ms": 0}
        t0 = time.time()
        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
                latency = (time.time() - t0) * 1000
                result["latency_ms"] = round(latency, 1)
                resp_text = await resp.text()

                try:
                    data = json.loads(resp_text)
                except json.JSONDecodeError:
                    result["status"] = "ERROR"
                    result["error"] = f"Non-JSON response (status={resp.status}): {resp_text[:200]}"
                    return result

                if resp.status == 200:
                    if "candidates" in data and data["candidates"]:
                        cand = data["candidates"][0]
                        finish_reason = cand.get("finishReason", "UNKNOWN")
                        if finish_reason == "SAFETY":
                            result["status"] = "SHADOWBANNED"
                            result["error"] = "Safety filter triggered"
                        elif finish_reason == "RECITATION":
                            result["status"] = "SHADOWBANNED"
                            result["error"] = "Recitation filter triggered"
                        else:
                            text = cand.get("content", {}).get("parts", [{}])[0].get("text", "")
                            if text.strip().upper() == "OK":
                                result["status"] = "OK"
                            elif any(r in text.lower() for r in ["i cannot", "i'm unable", "i apologize", "i am not able"]):
                                result["status"] = "SHADOWBANNED"
                                result["error"] = f"Refused: {text[:120]}"
                            else:
                                result["status"] = "OK"  # Got response, might not match exactly but works
                    elif "candidates" in data and not data["candidates"]:
                        result["status"] = "SHADOWBANNED"
                        result["error"] = "Empty candidates - likely blocked"
                    else:
                        result["status"] = "OK"
                elif resp.status == 429:
                    result["status"] = "RATE_LIMITED"
                    result["error"] = data.get("error", {}).get("message", "429 Too Many Requests")[:200]
                elif resp.status == 403:
                    msg = data.get("error", {}).get("message", "")
                    if "billing" in msg.lower() or "project" in msg.lower():
                        result["status"] = "BANNED"
                    else:
                        result["status"] = "BANNED"
                    result["error"] = msg[:200]
                elif resp.status == 400:
                    msg = data.get("error", {}).get("message", "")
                    status_lower = data.get("error", {}).get("status", "")
                    if "API_KEY_INVALID" in msg or "API_KEY_INVALID" in status_lower:
                        result["status"] = "INVALID_KEY"
                    elif "INVALID_ARGUMENT" in status_lower or "invalid" in msg.lower():
                        result["status"] = "MODEL_NOT_FOUND"
                    elif "billing" in msg.lower():
                        result["status"] = "BANNED"
                    else:
                        result["status"] = "ERROR"
                    result["error"] = msg[:200]
                elif resp.status == 404:
                    result["status"] = "MODEL_NOT_FOUND"
                    result["error"] = data.get("error", {}).get("message", "Model not found")[:200]
                elif resp.status in (500, 502, 503):
                    result["status"] = "SERVER_ERROR"
                    result["error"] = data.get("error", {}).get("message", f"HTTP {resp.status}")[:200]
                else:
                    result["status"] = "ERROR"
                    result["error"] = data.get("error", {}).get("message", f"HTTP {resp.status}")[:200]

        except asyncio.TimeoutError:
            result["status"] = "TIMEOUT"
            result["error"] = "Request timed out"
        except aiohttp.ClientError as e:
            result["status"] = "ERROR"
            result["error"] = str(e)[:200]
        except Exception as e:
            result["status"] = "ERROR"
            result["error"] = str(e)[:200]

        return result


def summarize_key(key_results: list[dict]) -> dict:
    """Summarize a key's results across all models."""
    ok_models = []
    rl_models = []
    sb_models = []
    banned = False
    invalid = False
    nf_models = []
    err_models = []

    for r in key_results:
        m = r["model"]
        s = r["status"]
        if s == "OK":
            ok_models.append(m)
        elif s == "RATE_LIMITED":
            rl_models.append(m)
        elif s == "SHADOWBANNED":
            sb_models.append(m)
        elif s == "BANNED":
            banned = True
            break
        elif s == "INVALID_KEY":
            invalid = True
            break
        elif s == "MODEL_NOT_FOUND":
            nf_models.append(m)
        else:
            err_models.append(m)

    # Determine overall
    if invalid:
        return {"overall": "INVALID_KEY", "detail": "Key is invalid", "ok": [], "rl": [], "sb": []}
    if banned:
        return {"overall": "BANNED", "detail": "Key is banned", "ok": [], "rl": [], "sb": []}

    if not ok_models and not rl_models and not sb_models and nf_models and len(nf_models) == len(key_results):
        return {"overall": "ALL_NOT_FOUND", "detail": "All models returned 404 - may indicate invalid key or region block", "ok": [], "rl": [], "sb": []}

    if ok_models:
        if sb_models:
            return {"overall": "OK_SHADOWBAN_SOME", "detail": f"OK on {len(ok_models)} models, shadowbanned on {len(sb_models)}", "ok": ok_models, "rl": rl_models, "sb": sb_models}
        if rl_models:
            return {"overall": "OK_RATE_LIMITED_SOME", "detail": f"OK on {len(ok_models)} models, rate-limited on {len(rl_models)}", "ok": ok_models, "rl": rl_models, "sb": sb_models}
        return {"overall": "OK", "detail": f"OK on {len(ok_models)} models", "ok": ok_models, "rl": [], "sb": []}

    if sb_models and not ok_models:
        return {"overall": "SHADOWBANNED_ALL", "detail": f"Shadowbanned on {len(sb_models)} models, 0 OK", "ok": [], "rl": rl_models, "sb": sb_models}

    if rl_models and not ok_models:
        return {"overall": "RATE_LIMITED_ALL", "detail": f"Rate-limited on {len(rl_models)} models, 0 OK", "ok": [], "rl": rl_models, "sb": sb_models}

    return {"overall": "MIXED_ERRORS", "detail": f"OK={len(ok_models)} RL={len(rl_models)} SB={len(sb_models)} NF={len(nf_models)} ERR={len(err_models)}", "ok": ok_models, "rl": rl_models, "sb": sb_models}


async def main():
    print("=" * 80)
    print("  GEMINI API KEY COMPREHENSIVE TEST SUITE v2")
    print("=" * 80)
    print(f"  Keys: {len(GEMINI_KEYS)}")
    print(f"  Models to test per key: {len(ALL_MODELS)}")
    print(f"  Total requests: {len(GEMINI_KEYS) * len(ALL_MODELS)}")
    print(f"  Concurrency: {CONCURRENT}")
    print(f"  Timeout: {TIMEOUT}s")
    print("=" * 80)
    print()

    sem = asyncio.Semaphore(CONCURRENT)

    # Phase 1: Quick pre-scan - test each key against just 2 reliable models
    # to quickly identify dead keys
    PRE_SCAN_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash"]
    print("--- PHASE 1: Quick pre-scan (2 models x 40 keys = 80 requests) ---\n")

    async with aiohttp.ClientSession() as session:
        pre_tasks = []
        for i, key in enumerate(GEMINI_KEYS):
            for model in PRE_SCAN_MODELS:
                pre_tasks.append((i, key, model, test_key_model(session, key, model, sem)))
        
        pre_results = {}
        gathered = await asyncio.gather(*[t[3] for t in pre_tasks])
        for (idx, key, model, _), res in zip(pre_tasks, gathered):
            if idx not in pre_results:
                pre_results[idx] = []
            pre_results[idx].append(res)

    # Categorize keys from pre-scan
    dead_indices = set()
    live_indices = set()
    uncertain_indices = set()

    for idx in range(len(GEMINI_KEYS)):
        results = pre_results.get(idx, [])
        statuses = [r["status"] for r in results]
        snippet = f"{GEMINI_KEYS[idx][:12]}...{GEMINI_KEYS[idx][-4:]}"
        
        if any(s == "INVALID_KEY" for s in statuses):
            dead_indices.add(idx)
            print(f"  [DEAD]  [{idx+1:02d}] {snippet} -> INVALID_KEY")
        elif any(s == "BANNED" for s in statuses):
            dead_indices.add(idx)
            print(f"  [DEAD]  [{idx+1:02d}] {snippet} -> BANNED")
        elif any(s == "OK" for s in statuses):
            live_indices.add(idx)
            ok_models = [r["model"] for r in results if r["status"] == "OK"]
            oks = ",".join(m.split("-")[-1] for m in ok_models)
            print(f"  [LIVE]  [{idx+1:02d}] {snippet} -> OK on {oks}")
        else:
            uncertain_indices.add(idx)
            status_summary = {r["status"]: r["model"] for r in results}
            print(f"  [????]  [{idx+1:02d}] {snippet} -> {status_summary}")

    print(f"\n  Pre-scan: {len(live_indices)} LIVE, {len(uncertain_indices)} uncertain, {len(dead_indices)} DEAD")

    if dead_indices:
        print(f"  Dead indices: {sorted(dead_indices)}")

    # Phase 2: Deep test live + uncertain keys against ALL models
    deep_indices = live_indices | uncertain_indices
    print(f"\n--- PHASE 2: Deep test {len(deep_indices)} keys x {len(ALL_MODELS)} models ---\n")

    if not deep_indices:
        print("  No keys to deep test. All keys are dead.")
        print("\n" + "=" * 80)
        print("  FINAL REPORT")
        print("=" * 80)
        print(f"\n  Total keys: {len(GEMINI_KEYS)}")
        print(f"  INVALID_KEY: {len(dead_indices)}")
        print(f"  ALL KEYS ARE DEAD - none usable")
        return

    all_summaries = {}
    async with aiohttp.ClientSession() as session:
        for idx in sorted(deep_indices):
            key = GEMINI_KEYS[idx]
            snippet = f"{key[:12]}...{key[-4:]}"
            
            tasks = [test_key_model(session, key, model, sem) for model in ALL_MODELS]
            model_results = await asyncio.gather(*tasks)
            
            summary = summarize_key(model_results)
            all_summaries[idx] = summary
            
            icon = {"OK": "[+]", "OK_SHADOWBAN_SOME": "[~S]", "OK_RATE_LIMITED_SOME": "[~R]",
                    "SHADOWBANNED_ALL": "[S!]", "RATE_LIMITED_ALL": "[R!]", "BANNED": "[XX]",
                    "INVALID_KEY": "[XX]", "ALL_NOT_FOUND": "[??]", "MIXED_ERRORS": "[??]"}.get(summary["overall"], "[??]")
            
            print(f"  {icon} [{idx+1:02d}] {snippet} -> {summary['overall']}: {summary['detail']}")
            
            # Show model-level details for non-OK results
            if summary["overall"] != "OK":
                for r in model_results:
                    if r["status"] != "OK":
                        icon_m = STATUS_ICONS.get(r["status"], "?")
                        print(f"       [{icon_m}] {r['model']}: {r['status']}")
                        if r["error"]:
                            print(f"           {r['error'][:150]}")
        
        # Also test dead keys against ALL models to confirm
        if dead_indices:
            print(f"\n--- PHASE 3: Confirm dead keys against all models ---\n")
            for idx in sorted(dead_indices):
                key = GEMINI_KEYS[idx]
                snippet = f"{key[:12]}...{key[-4:]}"
                tasks = [test_key_model(session, key, model, sem) for model in ALL_MODELS]
                model_results = await asyncio.gather(*tasks)
                summary = summarize_key(model_results)
                all_summaries[idx] = summary
                print(f"  [XX] [{idx+1:02d}] {snippet} -> {summary['overall']}: {summary['detail']}")

    # Final Report
    print("\n" + "=" * 80)
    print("  FINAL REPORT")
    print("=" * 80)

    status_counts = {}
    for idx, summary in all_summaries.items():
        ov = summary["overall"]
        status_counts[ov] = status_counts.get(ov, 0) + 1

    print(f"\n  Total keys tested: {len(GEMINI_KEYS)}")
    for status, count in sorted(status_counts.items()):
        print(f"  {status:25s}: {count}")

    # Detailed breakdown
    print("\n" + "-" * 40)
    print("  USABLE KEYS (OK or partial OK):")
    print("-" * 40)
    usable = {idx: s for idx, s in all_summaries.items() if s["overall"] in ("OK", "OK_SHADOWBAN_SOME", "OK_RATE_LIMITED_SOME")}
    if usable:
        for idx, summary in sorted(usable.items()):
            snippet = f"{GEMINI_KEYS[idx][:12]}...{GEMINI_KEYS[idx][-4:]}"
            print(f"  [{idx+1:02d}] {snippet}: {summary['overall']}")
            print(f"       OK models: {summary['ok']}")
            if summary.get("rl"):
                print(f"       Rate-limited models: {summary['rl']}")
            if summary.get("sb"):
                print(f"       Shadowbanned models: {summary['sb']}")
    else:
        print("  NONE")

    print("\n" + "-" * 40)
    print("  DEAD KEYS (remove from pool):")
    print("-" * 40)
    dead = {idx: s for idx, s in all_summaries.items() if s["overall"] in ("INVALID_KEY", "BANNED")}
    if dead:
        for idx, summary in sorted(dead.items()):
            snippet = f"{GEMINI_KEYS[idx][:12]}...{GEMINI_KEYS[idx][-4:]}"
            print(f"  [{idx+1:02d}] {snippet}: {summary['overall']} - {summary['detail']}")
    else:
        print("  NONE")

    print("\n" + "-" * 40)
    print("  PROBLEM KEYS (shadowbanned or rate-limited):")
    print("-" * 40)
    problem = {idx: s for idx, s in all_summaries.items() if s["overall"] in ("SHADOWBANNED_ALL", "RATE_LIMITED_ALL", "ALL_NOT_FOUND", "MIXED_ERRORS")}
    if problem:
        for idx, summary in sorted(problem.items()):
            snippet = f"{GEMINI_KEYS[idx][:12]}...{GEMINI_KEYS[idx][-4:]}"
            print(f"  [{idx+1:02d}] {snippet}: {summary['overall']} - {summary['detail']}")
    else:
        print("  NONE")

    # Model-level summary
    print("\n" + "-" * 40)
    print("  PER-MODEL SUCCESS RATE:")
    print("-" * 40)
    model_success = {}
    for idx, summary in all_summaries.items():
        for m in summary.get("ok", []):
            model_success[m] = model_success.get(m, 0) + 1
    for m in sorted(model_success, key=model_success.get, reverse=True):
        pct = model_success[m] / len(GEMINI_KEYS) * 100
        print(f"  {m:45s}: {model_success[m]:2d}/{len(GEMINI_KEYS)} ({pct:.0f}%)")

    print("\n" + "=" * 80)
    print("  TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
