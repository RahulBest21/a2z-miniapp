"""
Comprehensive Gemini API Key Tester
Tests each key for: validity, rate-limits, shadowbans, and model-specific bans.
"""
import asyncio
import time
import json
import sys
from typing import Optional

# 40 Gemini API keys from mainmock.py
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

PRIMARY_MODEL = "models/gemini-2.5-flash-preview-05-20-2025"
FALLBACK_MODELS = [
    "models/gemini-2.0-flash",
    "models/gemini-2.0-flash-lite",
    "models/gemini-1.5-flash",
]

TEST_PROMPT = "Reply with exactly the word: OK"

# ============================

try:
    import google.generativeai as genai
    GENA_AVAILABLE = True
except ImportError:
    GENA_AVAILABLE = False

import aiohttp


class KeyResult:
    __slots__ = ("index", "key_snippet", "status", "model_results", "error_detail")

    def __init__(self, index: int, key: str):
        self.index = index
        self.key_snippet = f"{key[:12]}...{key[-4:]}"
        self.status = "UNKNOWN"
        self.model_results = {}
        self.error_detail = ""


async def test_key_sdk(session, index: int, key: str, model_name: str, sem: asyncio.Semaphore) -> dict:
    """Test a key with google-generativeai SDK."""
    async with sem:
        result = {"model": model_name, "status": "UNKNOWN", "error": "", "latency_ms": 0}
        t0 = time.time()
        try:
            genai.configure(api_key=key, transport="rest")
            model = genai.GenerativeModel(model_name)
            response = await asyncio.wait_for(
                model.generate_content_async(TEST_PROMPT),
                timeout=30,
            )
            latency = (time.time() - t0) * 1000
            result["latency_ms"] = round(latency, 1)

            # Check for safety blocks / shadowban
            if response.candidates and response.candidates[0].finish_reason:
                fr = str(response.candidates[0].finish_reason)
                if "SAFETY" in fr:
                    result["status"] = "SHADOWBANNED"
                    result["error"] = f"Safety block: {fr}"
                elif "RECITATION" in fr:
                    result["status"] = "SHADOWBANNED"
                    result["error"] = f"Recitation block: {fr}"
                elif "STOP" in fr:
                    text = response.text.strip() if response.text else ""
                    if text.upper() == "OK":
                        result["status"] = "OK"
                    elif "I cannot" in text.lower() or "I'm unable" in text.lower() or "safety" in text.lower():
                        result["status"] = "SHADOWBANNED"
                        result["error"] = f"Refused response: {text[:120]}"
                    else:
                        result["status"] = "OK"
                elif "MAX_TOKENS" in fr:
                    result["status"] = "OK"
                else:
                    result["status"] = "WARN"
                    result["error"] = f"Finish reason: {fr}"
            elif response.text:
                result["status"] = "OK"
            else:
                result["status"] = "OK"
        except asyncio.TimeoutError:
            result["status"] = "TIMEOUT"
            result["error"] = "Request timed out after 30s"
        except Exception as e:
            err_str = str(e)
            latency = (time.time() - t0) * 1000
            result["latency_ms"] = round(latency, 1)

            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                result["status"] = "RATE_LIMITED"
                result["error"] = err_str[:200]
            elif "403" in err_str or "PERMISSION_DENIED" in err_str:
                result["status"] = "BANNED"
                result["error"] = err_str[:200]
            elif "400" in err_str and ("API_KEY_INVALID" in err_str or "API key not valid" in err_str.lower()):
                result["status"] = "INVALID_KEY"
                result["error"] = err_str[:200]
            elif "404" in err_str:
                result["status"] = "MODEL_NOT_FOUND"
                result["error"] = err_str[:200]
            elif "503" in err_str or "UNAVAILABLE" in err_str:
                result["status"] = "UNAVAILABLE"
                result["error"] = err_str[:200]
            elif "500" in err_str or "INTERNAL" in err_str:
                result["status"] = "SERVER_ERROR"
                result["error"] = err_str[:200]
            elif "SAFETY" in err_str:
                result["status"] = "SHADOWBANNED"
                result["error"] = err_str[:200]
            elif "blocked" in err_str.lower():
                result["status"] = "SHADOWBANNED"
                result["error"] = err_str[:200]
            else:
                result["status"] = "ERROR"
                result["error"] = err_str[:200]

        return result


async def test_key_rest(session: aiohttp.ClientSession, index: int, key: str, model_name: str, sem: asyncio.Semaphore) -> dict:
    """Test a key via REST API directly (fallback if SDK not available or as double-check)."""
    async with sem:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": TEST_PROMPT}]}],
            "generationConfig": {"maxOutputTokens": 50},
        }
        result = {"model": model_name, "status": "UNKNOWN", "error": "", "latency_ms": 0}
        t0 = time.time()
        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                latency = (time.time() - t0) * 1000
                result["latency_ms"] = round(latency, 1)
                data = await resp.json()

                if resp.status == 200:
                    if "candidates" in data:
                        cand = data["candidates"][0]
                        finish_reason = cand.get("finishReason", "UNKNOWN")
                        if finish_reason == "SAFETY":
                            result["status"] = "SHADOWBANNED"
                            result["error"] = f"Safety filter triggered"
                        else:
                            text = cand.get("content", {}).get("parts", [{}])[0].get("text", "")
                            if text.strip().upper() == "OK":
                                result["status"] = "OK"
                            elif "I cannot" in text or "I'm unable" in text:
                                result["status"] = "SHADOWBANNED"
                                result["error"] = f"Refused: {text[:120]}"
                            else:
                                result["status"] = "OK"
                    else:
                        result["status"] = "OK"
                elif resp.status == 429:
                    result["status"] = "RATE_LIMITED"
                    result["error"] = data.get("error", {}).get("message", "")[:200]
                elif resp.status == 403:
                    result["status"] = "BANNED"
                    result["error"] = data.get("error", {}).get("message", "")[:200]
                elif resp.status == 400:
                    msg = data.get("error", {}).get("message", "")
                    if "API_KEY_INVALID" in msg:
                        result["status"] = "INVALID_KEY"
                    else:
                        result["status"] = "BANNED"
                    result["error"] = msg[:200]
                elif resp.status == 404:
                    result["status"] = "MODEL_NOT_FOUND"
                    result["error"] = data.get("error", {}).get("message", "")[:200]
                elif resp.status in (500, 502, 503):
                    result["status"] = "SERVER_ERROR"
                    result["error"] = data.get("error", {}).get("message", "")[:200]
                else:
                    result["status"] = "ERROR"
                    result["error"] = data.get("error", {}).get("message", str(data))[:200]

        except asyncio.TimeoutError:
            result["status"] = "TIMEOUT"
            result["error"] = "Request timed out after 30s"
        except Exception as e:
            result["status"] = "ERROR"
            result["error"] = str(e)[:200]

        return result


def determine_overall_status(model_results: dict) -> tuple:
    """Determine overall status from per-model results."""
    statuses = [r["status"] for r in model_results.values() if r]
    if not statuses:
        return "UNKNOWN", ""
    if all(s == "OK" for s in statuses):
        return "OK", ""
    if all(s == "INVALID_KEY" for s in statuses):
        return "INVALID_KEY", model_results[next(iter(model_results))]["error"]
    if all(s == "BANNED" for s in statuses):
        return "BANNED", model_results[next(iter(model_results))]["error"]
    if all(s == "RATE_LIMITED" for s in statuses):
        return "RATE_LIMITED_ALL", "All models rate-limited for this key"
    if "OK" in statuses:
        if "RATE_LIMITED" in statuses:
            rl_models = [m for m, r in model_results.items() if r and r["status"] == "RATE_LIMITED"]
            return "PARTIAL_OK", f"OK on some models, rate-limited on: {', '.join(rl_models)}"
        if "SHADOWBANNED" in statuses:
            sb_models = [m for m, r in model_results.items() if r and r["status"] == "SHADOWBANNED"]
            return "PARTIAL_OK", f"OK on some models, shadowbanned on: {', '.join(sb_models)}"
        return "OK", ""
    if all(s == "SHADOWBANNED" for s in statuses):
        return "SHADOWBANNED", "All models safety-filtered — likely shadowbanned"
    if any(s == "SHADOWBANNED" for s in statuses):
        return "SHADOWBANNED", "Some models shadowbanned"
    if any(s == "RATE_LIMITED" for s in statuses):
        return "RATE_LIMITED", "Some models rate-limited"
    if any(s == "BANNED" for s in statuses):
        return "BANNED", "Key banned on some models"
    if any(s == "INVALID_KEY" for s in statuses):
        return "INVALID_KEY", "Key invalid on some models"
    return "MIXED", f"Mixed statuses: {set(statuses)}"


async def main():
    print("=" * 80)
    print("  GEMINI API KEY TEST SUITE")
    print("=" * 80)
    print(f"  Keys to test: {len(GEMINI_KEYS)}")
    print(f"  Primary model: {PRIMARY_MODEL}")
    print(f"  Fallback models: {FALLBACK_MODELS}")
    print(f"  SDK available: {GENA_AVAILABLE}")
    print("=" * 80)

    results = []
    sem = asyncio.Semaphore(5)  # Max 5 concurrent requests

    # Phase 1: Test primary model on all keys first (fast pre-scan)
    print("\n--- PHASE 1: Quick pre-scan with primary model ---")
    async with aiohttp.ClientSession() as session:
        tasks = [test_key_rest(session, i, key, PRIMARY_MODEL, sem) for i, key in enumerate(GEMINI_KEYS)]
        phase1_results = await asyncio.gather(*tasks)

    # Categorize
    valid_keys = []
    maybe_keys = []
    dead_keys = []
    for i, r in enumerate(phase1_results):
        key = GEMINI_KEYS[i]
        snippet = f"{key[:12]}...{key[-4:]}"
        if r["status"] == "OK":
            valid_keys.append((i, key, snippet, r))
            print(f"  [{i+1:02d}] {snippet} -> OK ({r['latency_ms']:.0f}ms)")
        elif r["status"] in ("INVALID_KEY", "BANNED"):
            dead_keys.append((i, key, snippet, r))
            print(f"  [{i+1:02d}] {snippet} -> {r['status']}: {r['error'][:100]}")
        else:
            maybe_keys.append((i, key, snippet, r))
            print(f"  [{i+1:02d}] {snippet} -> {r['status']}: {r['error'][:100]}")

    print(f"\n  Pre-scan summary: {len(valid_keys)} OK, {len(maybe_keys)} uncertain, {len(dead_keys)} dead")

    # Phase 2: Deep test — test all models on keys that weren't clearly dead
    print("\n--- PHASE 2: Deep test with all models ---")
    deep_keys = valid_keys + maybe_keys

    if not deep_keys:
        print("  No keys to deep-test.")
    else:
        all_models = [PRIMARY_MODEL] + FALLBACK_MODELS
        results = []
        async with aiohttp.ClientSession() as session:
            for idx, key, snippet, pre_result in deep_keys:
                kr = KeyResult(idx, key)
                kr.status = pre_result["status"]  # Start with pre-scan result

                tasks = [test_key_rest(session, idx, key, model, sem) for model in all_models]
                model_results_list = await asyncio.gather(*tasks)
                for mname, mres in zip(all_models, model_results_list):
                    kr.model_results[mname] = mres

                # Skip model_not_found for outdated model IDs and retry alternatives
                for mname, mres in list(kr.model_results.items()):
                    if mres["status"] == "MODEL_NOT_FOUND":
                        alt_model = None
                        if "2.5-flash-preview" in mname:
                            alt_model = "models/gemini-2.5-flash"
                        elif "2.0-flash" == mname.split("/")[-1]:
                            alt_model = "models/gemini-2.0-flash-001"
                        if alt_model and alt_model not in kr.model_results:
                            print(f"  [{idx+1:02d}] Retrying {mname} -> {alt_model}")
                            retry_res = await test_key_rest(session, idx, key, alt_model, sem)
                            kr.model_results[alt_model] = retry_res

                overall, detail = determine_overall_status(kr.model_results)
                kr.status = overall
                kr.error_detail = detail
                results.append(kr)

                # Print per-key summary
                status_icon = {"OK": "[+]", "PARTIAL_OK": "[~]", "RATE_LIMITED": "[R]", "RATE_LIMITED_ALL": "[R]",
                               "SHADOWBANNED": "[S]", "BANNED": "[X]", "INVALID_KEY": "[X]",
                               "ERROR": "[?]", "MIXED": "[?]"}.get(overall, "[?]")
                print(f"  {status_icon} [{idx+1:02d}] {snippet} -> {overall}: {detail[:120]}")
                for mname, mres in kr.model_results.items():
                    micon = {"OK": "  OK", "RATE_LIMITED": "  RL", "SHADOWBANNED": "  SB",
                             "BANNED": "  XX", "INVALID_KEY": "  XX", "ERROR": "  ??",
                             "MODEL_NOT_FOUND": "  NF", "SERVER_ERROR": "  SE",
                             "TIMEOUT": "  TO", "UNAVAILABLE": "  NA"}.get(mres["status"], "  --")
                    print(f"         {micon} {mname} ({mres['latency_ms']:.0f}ms)")

        # Phase 2 summary
        print("\n" + "=" * 80)
        print("  DEEP TEST SUMMARY")
        print("=" * 80)

        counts = {}
        for kr in results:
            counts[kr.status] = counts.get(kr.status, 0) + 1

        print(f"\n  Total keys tested: {len(results) + len(dead_keys)}")
        print(f"  Fully OK:          {counts.get('OK', 0)}")
        print(f"  Partially OK:      {counts.get('PARTIAL_OK', 0)}")
        print(f"  Rate Limited:      {counts.get('RATE_LIMITED', 0)}")
        print(f"  Rate Limited All:  {counts.get('RATE_LIMITED_ALL', 0)}")
        print(f"  Shadowbanned:      {counts.get('SHADOWBANNED', 0)}")
        print(f"  Banned:            {counts.get('BANNED', 0) + len(dead_keys)}")
        print(f"  Invalid Key:       {counts.get('INVALID_KEY', 0)}")
        print(f"  Errors/Other:      {counts.get('ERROR', 0) + counts.get('MIXED', 0)}")

        # Detailed breakdown
        print("\n--- Details ---")
        for kr in results:
            print(f"\n  Key {kr.key_snippet}: {kr.status}")
            if kr.error_detail:
                print(f"    Detail: {kr.error_detail}")
            for mname, mres in kr.model_results.items():
                if mres["status"] != "OK":
                    print(f"    {mname}: {mres['status']} — {mres['error'][:150]}")

        # Final recommendations
        print("\n" + "=" * 80)
        print("  RECOMMENDATIONS")
        print("=" * 80)
        good_keys = [kr for kr in results if kr.status in ("OK", "PARTIAL_OK")]
        if good_keys:
            print(f"\n  {len(good_keys)} usable keys found.")
            print("  Usable key indices (0-based):", [kr.index for kr in good_keys])
        else:
            print("\n  WARNING: No fully usable keys found!")

        dead_indices = [kr.index for kr in results if kr.status in ("BANNED", "INVALID_KEY")]
        dead_indices.extend(i for i, k, s, r in dead_keys)
        dead_indices.sort()
        if dead_indices:
            print(f"  Dead key indices (remove these): {dead_indices}")

        rl_indices = [kr.index for kr in results if kr.status in ("RATE_LIMITED", "RATE_LIMITED_ALL")]
        if rl_indices:
            print(f"  Rate-limited key indices: {rl_indices}")

        sb_indices = [kr.index for kr in results if kr.status == "SHADOWBANNED"]
        if sb_indices:
            print(f"  Shadowbanned key indices: {sb_indices}")

    print("\n" + "=" * 80)
    print("  TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
