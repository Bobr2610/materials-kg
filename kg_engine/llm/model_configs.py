"""Centralized model configuration registry.

Defines context windows, max output tokens, and default temperatures
for supported models. Kept separate for clarity and easier maintenance.
"""

from __future__ import annotations

MODEL_CONFIGS: dict[str, dict] = {
    # Gemini models (matching cmw-platform-agent)
    "gemini-2.5-flash": {
        "token_limit": 1_048_576,  # 1M context
        "max_tokens": 65_536,
        "temperature": 0,
    },
    "gemini-2.5-pro": {
        "token_limit": 1_048_576,  # 1M context
        "max_tokens": 65_536,
        "temperature": 0,
    },
    "google/gemini-3-flash-preview": {
        "token_limit": 1_048_576,  # 1M context window as per OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
    },
    "google/gemini-3.1-flash-lite-preview": {
        "token_limit": 1_048_576,  # 1M context window as per OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
    },
    # OpenRouter models (matching cmw-platform-agent)
    # DeepSeek Models
    "deepseek/deepseek-v3.1-terminus": {
        "token_limit": 163_840,
        "max_tokens": 65_536,
        "temperature": 0,
    },
    "deepseek/deepseek-v3.1-terminus:exacto": {
        "token_limit": 163_840,
        "max_tokens": 65_536,
        "temperature": 0,
    },
    "deepseek/deepseek-v3.2-speciale": {
        "token_limit": 163_840,  # OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
    },
    "deepseek/deepseek-chat-v3.1:free": {
        "token_limit": 163_840,
        "max_tokens": 4_096,
        "temperature": 0,
    },
    "deepseek/deepseek-r1-0528": {
        "token_limit": 163_840,
        "max_tokens": 4_096,
        "temperature": 0,
    },
    "deepseek/deepseek-v4-pro": {
        "token_limit": 1_048_576,  # 1M context window as per OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
        "supports_forced_tool_choice": False,  # tool_choice not supported in thinking mode
    },
    "deepseek/deepseek-v4-flash": {
        "token_limit": 1_048_576,  # 1M context window as per OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
        "supports_forced_tool_choice": False,  # tool_choice not supported in thinking mode
    },
    # Grok (xAI) Models
    "x-ai/grok-4-fast:free": {
        "token_limit": 2_000_000,
        "max_tokens": 8_192,
        "temperature": 0,
    },
    "x-ai/grok-code-fast-1": {
        "token_limit": 256_000,
        "max_tokens": 10_000,
        "temperature": 0,
    },
    "x-ai/grok-4-fast": {
        "token_limit": 2_000_000,
        "max_tokens": 30_000,
        "temperature": 0,
    },
    # Qwen Models
    "qwen/qwen3-coder:free": {
        "token_limit": 262_144,
        "max_tokens": 4_096,
        "temperature": 0,
    },
    "qwen/qwen3-coder-flash": {
        "token_limit": 128_000,
        "max_tokens": 4_096,
        "temperature": 0,
    },
    "qwen/qwen3-max": {
        "token_limit": 256_000,
        "max_tokens": 32_768,
        "temperature": 0,
    },
    "qwen/qwen3.5-flash-02-23": {
        "token_limit": 1_000_000,  # 1M context window as per OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
        "supports_forced_tool_choice": False,  # OpenRouter Qwen 3.5 models don't honor explicit tool_choice
    },
    "qwen/qwen3.5-122b-a10b": {
        "token_limit": 262_144,  # 262,144 context window as per OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
        "supports_forced_tool_choice": False,  # OpenRouter Qwen 3.5 models don't honor explicit tool_choice
    },
    "qwen/qwen3.5-35b-a3b": {
        "token_limit": 262_144,  # 262,144 context window as per OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
        "supports_forced_tool_choice": False,  # OpenRouter Qwen 3.5 models don't honor explicit tool_choice
    },
    "qwen/qwen3.5-27b": {
        "token_limit": 262_144,  # 262,144 context window as per OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
        "supports_forced_tool_choice": False,  # OpenRouter Qwen 3.5 models don't honor explicit tool_choice
    },
    "qwen/qwen3.5-9b": {
        "token_limit": 256_000,  # 256,000 context window as per OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
        "supports_forced_tool_choice": False,  # OpenRouter Qwen 3.5 models don't honor explicit tool_choice
    },
    # Additional Qwen Models
    "qwen/qwen3-235b-a22b": {
        # Native window ~40,960; some routes may extend via scaling
        "token_limit": 262_144,
        "max_tokens": 32_768,
        "temperature": 0,
    },
    "qwen/qwen3-30b-a3b-instruct-2507": {
        "token_limit": 262_144,
        "max_tokens": 32_768,
        "temperature": 0,
    },
    # vLLM Qwen model (with capital letters, matches vLLM max_model_len=40000)
    "Qwen/Qwen3-30B-A3B-Instruct-2507": {
        "token_limit": 40_000,  # Matches vLLM max_model_len configuration
        "max_tokens": 40_000,  # Matches LLM_MAX_TOKENS in .env
        "temperature": 0,
    },
    # vLLM Mistral model (matches vLLM max_model_len=32768)
    "mistralai/Ministral-3-14B-Instruct-2512": {
        "token_limit": 32768,  # Matches vLLM max_model_len configuration
        "max_tokens": 32768,  # Matches model's context window
        "temperature": 0,
    },
    # vLLM OSS-20 model (matches vLLM max_model_len=40000)
    "openai/gpt-oss-20b": {
        "token_limit": 40000,  # Matches vLLM max_model_len configuration
        "max_tokens": 40000,  # Matches vLLM max_model_len configuration
        "temperature": 0,
        "harmony_format": True,  # GPT-OSS models use Harmony response format
    },
    # vLLM GigaChat3 model (MoE: 10B total, 1.8B active params)
    # Supports up to 256K context window, optimized for high throughput
    "ai-sage/GigaChat3-10B-A1.8B-bf16": {
        "token_limit": 256_000,  # 256K context window as per model card
        "max_tokens": 65_536,  # Reasonable max output for large context model
        "temperature": 0,
    },
    # vLLM GigaChat3 fp8 model (optimized for high throughput inference)
    # MoE architecture with MLA and MTP, supports up to 256K context window
    "ai-sage/GigaChat3-10B-A1.8B": {
        "token_limit": 256_000,  # 256K context window as per model card
        "max_tokens": 65_536,  # Reasonable max output for large context model
        "temperature": 0,
    },
    # vLLM Qwen3-Coder-REAP model (REAP: Router-weighted Expert Activation Pruning)
    # Memory-efficient variant of Qwen3-Coder series, 25B total params
    "cerebras/Qwen3-Coder-REAP-25B-A3B": {
        "token_limit": 262_144,  # 256K context window, consistent with Qwen3 models
        "max_tokens": 32_768,  # Reasonable max output for code generation
        "temperature": 0,
    },
    "qwen/qwen3-coder-plus": {
        "token_limit": 128_000,
        "max_tokens": 65_536,
        "temperature": 0,
    },
    "qwen/qwen3-235b-a22b-2507": {
        "token_limit": 262_144,
        "max_tokens": 32_768,
        "temperature": 0,
    },
    "qwen/qwen3-coder": {
        "token_limit": 262_144,
        "max_tokens": 262_144,
        "temperature": 0,
    },
    # Other Models
    "anthropic/claude-sonnet-4.5": {
        "token_limit": 1_000_000,
        "max_tokens": 64_000,
        "temperature": 0,
    },
    "anthropic/claude-haiku-4.5": {
        "token_limit": 200_000,  # OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
    },
    "anthropic/claude-sonnet-4.6": {
        "token_limit": 1_000_000,  # OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
    },
    "anthropic/claude-opus-4.6": {
        "token_limit": 1_000_000,  # OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
    },
    "openai/gpt-5.3-codex": {
        "token_limit": 400_000,  # OpenRouter model card
        "max_tokens": 32_768,
        "temperature": 0,
    },
    "openai/gpt-5.3-chat": {
        "token_limit": 128_000,  # OpenRouter model card
        "max_tokens": 32_768,
        "temperature": 0,
    },
    "openai/gpt-oss-120b": {
        "token_limit": 131_072,
        "max_tokens": 32_768,
        "temperature": 0,
        "harmony_format": True,  # GPT-OSS models use Harmony response format
    },
    "openai/gpt-oss-120b:exacto": {
        "token_limit": 131_072,
        "max_tokens": 32_768,
        "temperature": 0,
        "harmony_format": True,  # GPT-OSS models use Harmony response format
    },
    "openai/gpt-5-mini": {
        "token_limit": 400_000,
        "max_tokens": 32_768,
        "temperature": 0,
    },
    "nvidia/nemotron-nano-9b-v2:free": {
        "token_limit": 128_000,
        "max_tokens": 4_096,
        "temperature": 0,
    },
    "mistralai/codestral-2508": {
        "token_limit": 256_000,
        "max_tokens": 4_096,
        "temperature": 0,
    },
    # Z.AI Models
    "z-ai/glm-4.7": {
        "token_limit": 202_752,  # 202,752 context window as per OpenRouter API
        "max_tokens": 32_768,  # Reasonable max output for large context model
        "temperature": 0,
    },
    "z-ai/glm-4.7-flash": {
        "token_limit": 200_000,  # 202,752 context window as per OpenRouter API
        "max_tokens": 32_768,  # Reasonable max output for large context model
        "temperature": 0,
    },
    "z-ai/glm-5": {
        "token_limit": 198_000,  # OpenRouter model card
        "max_tokens": 32_768,
        "temperature": 0,
    },
    # Moonshot AI (Kimi) Models
    "moonshotai/kimi-k2.5": {
        "token_limit": 262_144,  # 262.1K context window
        "max_tokens": 65_536,
        "temperature": 0,
    },
    # Minimax Models
    "minimax/minimax-m2.1": {
        "token_limit": 196_000,  # 196.6K context window
        "max_tokens": 65_536,
        "temperature": 0,
    },
    "minimax/minimax-m2.5": {
        "token_limit": 196_000,  # OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
    },
    "minimax/minimax-m3": {
        "token_limit": 524_288,  # 524.3K total context as per OpenRouter model card
        "max_tokens": 65_536,
        "temperature": 0,
        "supports_forced_tool_choice": False,  # OpenRouter endpoints don't support tool_choice for this model
    },
    # OpenAI specialized models
    "openai/gpt-5-codex": {
        "token_limit": 400_000,
        "max_tokens": 32_768,
        "temperature": 0,
    },
    # Fallback default
    "default": {
        "token_limit": 8_192,
        "max_tokens": 2_048,
        "temperature": 0.1,
    },
}
