"""
LLM factory for the ThermoPulse agent.

Configurable via env vars so the same agent code works with whichever
provider you have a key for. Defaults to OpenRouter (one API key, access to
many stable, well-known models — good fit for a hackathon where reliability
during the live demo matters more than squeezing out max performance).

    LLM_PROVIDER=openrouter   (default)
    OPENROUTER_API_KEY=...
    OPENROUTER_MODEL=openrouter/free   (default)
    # openrouter/free is OpenRouter's own auto-router: it picks a live free
    # model that supports tool calling, so this never breaks even as the
    # free-model roster rotates (which it does often). To pin a specific
    # model instead, check the current free list at openrouter.ai/models
    # (filter: Free) before hardcoding an ID — they get delisted with little
    # notice, as we just saw with google/gemini-2.0-flash-exp:free.

    LLM_PROVIDER=gemini
    GOOGLE_API_KEY=...
    GEMINI_MODEL=gemini-2.0-flash               (default)

    LLM_PROVIDER=openai
    OPENAI_API_KEY=...
    OPENAI_MODEL=gpt-4o-mini                     (default)
"""

from __future__ import annotations

import os


def get_llm():
    """Return a LangChain chat model based on LLM_PROVIDER (default: openrouter)."""
    provider = os.environ.get("LLM_PROVIDER", "openrouter").lower()

    if provider == "openrouter":
        from langchain_openai import ChatOpenAI

        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is not set. Add it to your .env file "
                "(get one free at https://openrouter.ai/keys)."
            )
        model = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0.2,
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY is not set. Add it to your .env file "
                "(get one free at https://aistudio.google.com/apikey)."
            )
        model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=0.2)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set. Add it to your .env file.")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        return ChatOpenAI(model=model, api_key=api_key, temperature=0.2)

    raise ValueError(
        f"Unsupported LLM_PROVIDER: {provider!r} (supported: openrouter, gemini, openai)"
    )