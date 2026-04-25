import asyncio
import json
import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import discord

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cogs.conversation_ai import ConversationAI


class MockDiscordUser:
    """Mock Discord user for testing"""
    def __init__(self, user_id: int, display_name: str, name: str = None):
        self.id = user_id
        self.display_name = display_name
        self.name = name if name is not None else display_name.lower().replace(' ', '_')
        self.bot = False


class MockDiscordChannel:
    """Mock Discord channel for testing"""
    def __init__(self, channel_id: int, name: str = "test-channel"):
        self.id = channel_id
        self.name = name


class MockDiscordGuild:
    """Mock Discord guild for testing"""
    def __init__(self, guild_id: int, name: str = "Test Server"):
        self.id = guild_id
        self.name = name


class MockDiscordMessage:
    """Mock Discord message for testing"""
    def __init__(self, content: str, user: MockDiscordUser, channel: MockDiscordChannel, guild: MockDiscordGuild = None, message_id: int = None):
        self.content = content
        self.author = user
        self.channel = channel
        self.guild = guild
        self.created_at = datetime.now()
        self.id = message_id if message_id is not None else hash(content + str(user.id) + str(channel.id)) % 1000000


class MockOllamaClient:
    """Mock Ollama client for controlled testing"""
    def __init__(self):
        self.current_model = "llama3.1:8b"
        self.responses = {}
        
    def get_current_model(self):
        return self.current_model
    
    def _build_context_string(self, user_name, message, channel_name=None, server_name=None, is_dm=False, conversation_history=None):
        """Helper method to build context string in the expected format"""
        context_lines = []
        
        # Add conversation history if provided
        if conversation_history:
            context_lines.append("=== RECENT CONVERSATION CONTEXT ===")
            for hist_msg in conversation_history:
                # Format timestamp to match real code: YYYY-MM-DD HH:MM
                timestamp = hist_msg['timestamp'][:16].replace('T', ' ') if 'T' in hist_msg['timestamp'] else hist_msg['timestamp']
                author_name = hist_msg.get('author_name', hist_msg.get('author', user_name))
                context_lines.append(f"[{timestamp}] {author_name}: {hist_msg['content']}")
            context_lines.append("=== END CONTEXT ===\n")
        
        # Add message to analyze
        context_lines.append("=== MESSAGE TO ANALYZE ===")
        context_lines.append(f"User: {user_name}")
        context_lines.append(f"Message: {message}")
        
        if is_dm:
            context_lines.append("Context: Direct Message (DM) with bot")
        else:
            if channel_name:
                context_lines.append(f"Channel: #{channel_name}")
            if server_name:
                context_lines.append(f"Server: {server_name}")
                
        return "\n".join(context_lines)
        
    async def generate_with_metadata(self, messages):
        """Return controlled responses based on message content"""
        user_content = messages[-1]["content"]
        
        # Return predefined responses based on content
        if user_content in self.responses:
            return self.responses[user_content]
            
        # Default response structure
        return {
            "metadata": {
                "topics": ["general"],
                "is_notable": False,
                "notable_reason": "",
                "user_insights": ["basic user"],
                "sentiment": "neutral",
                "contains_personal_info": False,
                "directed_at_bot_probability": 0.0,
                "bot_direction_reason": "Not directed at bot"
            }
        }
    
    def set_response(self, message_content: str, response_data: dict):
        """Set a specific response for testing"""
        self.responses[message_content] = response_data


class MockFileRepo:
    """Mock file repository for testing"""
    def __init__(self):
        self.files = {}
        self.file_contents = {}
        
    def find(self, filename):
        if filename in self.files:
            return MockFile(filename, f"/mock/path/{filename}.json")
        return None
        
    def add_file(self, filename):
        self.files[filename] = True
        return MockFile(filename, f"/mock/path/{filename}")
        
    def update_file(self, file_obj):
        pass
        
    def delete_file(self, filename):
        if filename in self.files:
            del self.files[filename]
            
    def list_files(self):
        return [MockFile(name, f"/mock/path/{name}") for name in self.files.keys()]
        
    def get_file_count(self):
        return len(self.files)


class MockFile:
    """Mock file object"""
    def __init__(self, name, path):
        self.name = name
        self.path = path
        
    def exists(self):
        return True


@pytest.fixture
def mock_bot():
    """Mock Discord bot"""
    bot = MagicMock()
    bot.user = MockDiscordUser(12345, "TestBot", "testbot")
    return bot


@pytest.fixture
def mock_ollama():
    """Mock Ollama client"""
    return MockOllamaClient()


@pytest.fixture
def mock_memory_repo():
    """Mock memory repository"""
    return MockFileRepo()


@pytest.fixture
def conversation_ai(mock_bot, mock_ollama, mock_memory_repo):
    """Conversation AI cog instance for testing"""
    return ConversationAI(mock_bot, mock_ollama, mock_memory_repo)


@pytest.fixture
def sample_user():
    """Sample Discord user for testing"""
    return MockDiscordUser(67890, "TestUser")


@pytest.fixture
def sample_channel():
    """Sample Discord channel for testing"""
    return MockDiscordChannel(11111, "general")


@pytest.fixture
def sample_guild():
    """Sample Discord guild for testing"""
    return MockDiscordGuild(22222, "Test Server") 