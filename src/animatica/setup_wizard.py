"""Interactive setup wizard: choose provider, store a key, run doctor checks."""
from __future__ import annotations

import getpass

from animatica.config import Config, save_config, save_key
from animatica.doctor import run_checks


def setup() -> None:
    """Walk the user through first-time setup."""
    print("Animatica setup")
    print("======================")
    print("Choose an AI provider:")
    print("  1. template   (offline, no key; only a few canned example prompts)")
    print("  2. groq       (cloud, free tier)        key: console.groq.com/keys")
    print("  3. openrouter (cloud, :free models)     key: openrouter.ai/keys")
    print("  4. nim        (cloud, free tier)        key: build.nvidia.com")
    print("  5. ollama     (local, no key, no cloud) install: ollama.com, then `ollama pull llama3.1`")
    choice = input("Provider [1-5]: ").strip() or "1"
    mapping = {"1": "template", "2": "groq", "3": "openrouter", "4": "nim", "5": "ollama"}
    provider = mapping.get(choice, "template")

    cloud = provider in ("groq", "openrouter", "nim")
    cloud_allowed = False
    key = None
    if cloud:
        ans = input("Allow cloud access? (y/N): ").strip().lower()
        cloud_allowed = ans == "y"
        if cloud_allowed:
            key = getpass.getpass(f"Paste your {provider} API key (input hidden): ").strip()

    cfg = Config(provider=provider, cloud_allowed=cloud_allowed)
    save_config(cfg)
    if key:
        save_key(provider, key)
        print(f"Key stored for {provider} (mode 600).")
    else:
        print("No key stored (offline/template mode).")

    print("\nRunning doctor checks...")
    checks = run_checks()
    failures = 0
    for c in checks:
        mark = "OK " if c.ok else "FAIL"
        print(f"  [{mark}] {c.name}: {c.detail}")
        if not c.ok and c.fix:
            print(f"         fix: {c.fix}")
            failures += 1
    if failures:
        print(f"\n{failures} check(s) failed. Fix them, then run 'animatica doctor' again.")
    else:
        print("\nAll checks passed. You're ready to run 'animatica make ...'.")

