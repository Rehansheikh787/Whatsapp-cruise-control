"""
agent/test_generator.py

Unit and integration tests for agent/generator.py.
Verifies prompt construction, few-shot formatting, fallback behavior on empty retrieval or API issues.
"""

from unittest.mock import MagicMock, patch

import pytest

from agent.generator import generate_reply


def test_generator_with_retrieved_pairs():
    fake_retrieved = [
        {"their_message": "kaha hai?", "my_reply": "ghar pe hu", "distance": 1.1},
        {"their_message": "kab aayega?", "my_reply": "thodi der me", "distance": 1.2},
    ]
    fake_response = MagicMock()
    fake_response.text = "Bas nikal raha hu bhai"

    with patch("agent.generator.retrieve_similar", return_value=fake_retrieved) as mock_retrieval, \
         patch("agent.generator.client.models.generate_content", return_value=fake_response) as mock_model:
        
        reply = generate_reply("kaha hai bhai?", "friend")
        assert reply == "Bas nikal raha hu bhai"
        
        mock_retrieval.assert_called_once_with(relationship="friend", incoming_message="kaha hai bhai?", k=3)
        prompt_arg = mock_model.call_args[1]["contents"]
        assert "Here are real examples" in prompt_arg
        assert 'Their message: "kaha hai?"' in prompt_arg
        assert 'My reply: "ghar pe hu"' in prompt_arg


def test_generator_with_empty_retrieved_pairs():
    # Empty retrieval shouldn't crash; few-shot section should be absent
    fake_response = MagicMock()
    fake_response.text = "Hello sir, yes please."

    with patch("agent.generator.retrieve_similar", return_value=[]) as mock_retrieval, \
         patch("agent.generator.client.models.generate_content", return_value=fake_response) as mock_model:
        
        reply = generate_reply("Good morning", "professional")
        assert reply == "Hello sir, yes please."
        
        prompt_arg = mock_model.call_args[1]["contents"]
        assert "Here are real examples" not in prompt_arg


def test_generator_handles_retrieval_exception():
    # If Chroma fails or raises, generator must not crash
    fake_response = MagicMock()
    fake_response.text = "Haa mummy sab thik hai"

    with patch("agent.generator.retrieve_similar", side_effect=Exception("Chroma down")), \
         patch("agent.generator.client.models.generate_content", return_value=fake_response):
        
        reply = generate_reply("Khana kha liya?", "family")
        assert reply == "Haa mummy sab thik hai"


def test_generator_empty_model_response():
    # Model returns empty string (safety filter block)
    fake_response = MagicMock()
    fake_response.text = ""

    with patch("agent.generator.retrieve_similar", return_value=[]), \
         patch("agent.generator.client.models.generate_content", return_value=fake_response):
        
        reply = generate_reply("Hello", "friend")
        assert reply == "[no reply generated — check response.candidates for details]"


def test_generator_handles_api_exception():
    # Model throws exception (network issue, quota, etc.)
    with patch("agent.generator.retrieve_similar", return_value=[]), \
         patch("agent.generator.client.models.generate_content", side_effect=Exception("API Timeout")):
        
        reply = generate_reply("Hello", "friend")
        assert reply == "[no reply generated — check response.candidates for details]"
