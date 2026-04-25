"""
ConversationAI tests have been split into focused modules:

- conftest.py: Shared fixtures and mock classes
- test_conversation_ai_core.py: Core functionality tests  
- test_message_storage.py: Message storage and history tests
- test_memory_persistence.py: Memory persistence and backfill tests

Run all tests with: pytest tests/
"""

import pytest

if __name__ == "__main__":
    pytest.main(["-v", "tests/"]) 