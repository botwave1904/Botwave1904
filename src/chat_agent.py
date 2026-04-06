#!/usr/bin/env python3
"""
Botwave Chat Agent - Your AI Companion
Talk to this agent like you're talking to Claude.
Uses your local LLM or API providers.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    import requests
except ImportError:
    print("Installing requests...")
    os.system(f"{sys.executable} -m pip install requests -q")
    import requests


class ChatAgent:
    """AI chat agent with memory and personality."""

    def __init__(self):
        self.name = "Botwave"
        self.user = "Business Owner"
        self.memory = []
        self.max_memory = 20

        # Load config from .env
        self.api_url = os.getenv("LLM_API_URL", "http://localhost:1234/v1")
        self.api_key = os.getenv("LLM_API_KEY", "lm-studio")
        self.model = os.getenv("LLM_MODEL", "local-model")

        # Try OpenRouter if local LLM not available
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

        self.system_prompt = f"""You are {self.name}, an AI assistant for {self.user}.
You are helpful, direct, and focused on business automation and IT services.
{self.user} built you to help run their Botwave Empire business.

Key facts:
- Business: AI automation for service businesses (plumbers, HVAC, contractors)
- Current client: Dad's plumbing business (Jimenez Plumbing)
- Goal: Scale to baby boomer small business owners

Be concise but thorough. Help {self.user} succeed."""

    def query_local_llm(self, messages: list) -> str:
        """Query local LM Studio instance."""
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "lm-studio":
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2000
        }

        try:
            response = requests.post(
                f"{self.api_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[Local LLM Error: {e}. Is LM Studio running?]"

    def query_openrouter(self, messages: list) -> str:
        """Query OpenRouter API."""
        if not self.openrouter_key:
            return None

        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "anthropic/claude-3.5-sonnet",
            "messages": messages,
            "max_tokens": 2000
        }

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[OpenRouter Error: {e}]"

    def chat(self, user_input: str) -> str:
        """Process user input and respond."""
        # Add to memory
        self.memory.append({"role": "user", "content": user_input})

        # Build messages
        messages = [
            {"role": "system", "content": self.system_prompt}
        ] + self.memory[-self.max_memory:]

        # Try local LLM first
        response = self.query_local_llm(messages)

        # Fallback to OpenRouter if local fails
        if "Error" in response and self.openrouter_key:
            response = self.query_openrouter(messages)

        # Add response to memory
        self.memory.append({"role": "assistant", "content": response})

        return response

    def clear_memory(self):
        """Clear conversation memory."""
        self.memory = []
        return "Memory cleared. Starting fresh."

    def interactive(self):
        """Start interactive chat session."""
        print("\n" + "="*60)
        print(f"  {self.name.upper()} - CHAT AGENT")
        print("  Type 'exit' to quit, 'clear' to reset memory")
        print("="*60 + "\n")

        print(f"{self.name}: Hey {self.user}! I'm ready to help with your Botwave Empire.")
        print("What's on your mind?\n")

        while True:
            try:
                user_input = input(f"{self.user}: ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ['exit', 'quit', 'bye']:
                    print(f"\n{self.name}: Later, boss. Good luck with everything!")
                    break

                if user_input.lower() in ['clear', 'reset', 'forget']:
                    self.clear_memory()
                    print(f"{self.name}: Got it. Fresh start.\n")
                    continue

                if user_input.lower() in ['help', '?']:
                    print(f"\n{self.name}: Commands:")
                    print("  - Just talk to me naturally")
                    print("  - 'clear' - Reset conversation memory")
                    print("  - 'exit' - End chat session\n")
                    continue

                # Get response
                response = self.chat(user_input)
                print(f"\n{self.name}: {response}\n")

            except KeyboardInterrupt:
                print(f"\n\n{self.name}: Catch you later!")
                break
            except Exception as e:
                print(f"\n{self.name}: Oops, error: {e}\n")


def main():
    """Run the chat agent."""
    # Load .env
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, val = line.strip().split('=', 1)
                    os.environ.setdefault(key, val)

    agent = ChatAgent()
    agent.interactive()


if __name__ == "__main__":
    main()