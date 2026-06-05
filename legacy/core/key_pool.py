import os
import time

class KeyPool:
    """
    Manages up to 20 API keys per provider.
    Rotates to next key on HTTP 429 (rate limit).
    Re-enables exhausted keys after a cooldown period (e.g. 60 seconds).
    """
    def __init__(self, cooldown_seconds: float = 60.0) -> None:
        self.cooldown_seconds = cooldown_seconds
        
        # Load keys from environment
        self._keys: dict[str, list[str]] = {
            "gemini": [],
            "anthropic": [],
            "openai": []
        }
        
        for provider, env_prefix in [("gemini", "GEMINI_API_KEY"), 
                                     ("anthropic", "ANTHROPIC_API_KEY"),
                                     ("openai", "OPENAI_API_KEY")]:
            # Check base key
            if base_key := os.environ.get(env_prefix):
                self._keys[provider].append(base_key)
                
            # Check 1 to 20
            for i in range(1, 21):
                if key := os.environ.get(f"{env_prefix}_{i}"):
                    self._keys[provider].append(key)
                    
        self._exhausted: dict[str, float] = {}  # key -> timestamp when it was exhausted
        self._current_index: dict[str, int] = {p: 0 for p in self._keys}

    def _refresh_exhausted(self) -> None:
        now = time.time()
        to_remove = []
        for key, ts in self._exhausted.items():
            if now - ts >= self.cooldown_seconds:
                to_remove.append(key)
        for key in to_remove:
            del self._exhausted[key]

    def next_key(self, provider: str, default_key: str | None = None) -> str | None:
        """Get the next available key for a provider."""
        self._refresh_exhausted()
        
        keys = self._keys.get(provider, [])
        if not keys:
            return default_key
            
        start_idx = self._current_index[provider]
        
        for i in range(len(keys)):
            idx = (start_idx + i) % len(keys)
            key = keys[idx]
            if key not in self._exhausted:
                self._current_index[provider] = (idx + 1) % len(keys)
                return key
                
        # All keys exhausted, return the default or the first one as fallback
        return default_key if default_key else keys[0]

    def mark_exhausted(self, provider: str, key: str) -> None:
        """Mark a key as exhausted (HTTP 429)."""
        if provider in self._keys and key in self._keys[provider]:
            self._exhausted[key] = time.time()
