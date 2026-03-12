from typing import List, Dict, Any
import ollama
import openrouter
import groq

class AIOrchestrator:
    def __init__(self):
        self.providers = {
            'ollama': ollama.Client(),
            'openrouter': openrouter.Client(),
            'groq': groq.Client()
        }
    
    def generate_strategy(self, context: Dict[str, Any]) -> str:
        """Generate strategy using multiple AI providers"""
        providers = ['ollama', 'groq', 'openrouter']
        responses = []
        
        for provider_name in providers:
            try:
                response = self.providers[provider_name].generate(
                    prompt=f"Fleet management strategy for context: {context}",
                    max_tokens=500
                )
                responses.append(response)
            except Exception as e:
                print(f"Error with {provider_name}: {e}")
        
        # Consensus mechanism
        return max(set(responses), key=responses.count)
    
    def validate_strategy(self, strategy: str) -> bool:
        """Validate generated strategy across providers"""
        validation_scores = []
        for provider in self.providers.values():
            score = provider.evaluate_strategy(strategy)
            validation_scores.append(score)
        
        return sum(validation_scores) / len(validation_scores) > 0.7