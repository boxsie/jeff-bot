import pytest
import json
from datetime import datetime
from unittest.mock import patch
from conftest import MockFileRepo


class TestMemoryPersistence:
    """Test memory persistence functionality"""
    
    @pytest.mark.asyncio
    async def test_save_user_memory(self, conversation_ai, mock_memory_repo, sample_user):
        """Test saving user memory to file repository"""
        # Add user memory
        user_id = sample_user.id
        conversation_ai.user_memories[user_id] = {
            'user_name': sample_user.display_name,
            'interaction_count': 5,
            'topics_discussed': ['test', 'memory'],
            'personality_notes': ['test user'],
            'sentiment_history': [{'sentiment': 'positive', 'timestamp': datetime.now().isoformat()}]
        }
        
        # Mock file operations
        with patch('builtins.open', create=True) as mock_open:
            with patch('json.dump') as mock_json_dump:
                conversation_ai._save_user_memory(user_id)
                
                # Verify file operations were called
                mock_open.assert_called()
                mock_json_dump.assert_called()
                
    def test_load_memories_empty_repo(self, mock_bot, mock_ollama):
        """Test loading memories with empty repository"""
        from cogs.conversation_ai import ConversationAI
        
        empty_repo = MockFileRepo()
        cog = ConversationAI(mock_bot, mock_ollama, empty_repo)
        
        # Should initialize with empty memories
        assert len(cog.user_memories) == 0
        assert len(cog.general_insights) == 0


class TestBackfillFunctionality:
    """Test message history backfill functionality"""
    
    def test_backfill_initialization(self, conversation_ai):
        """Test that backfill flag is properly initialized"""
        assert hasattr(conversation_ai, 'history_backfilled')
        assert conversation_ai.history_backfilled == False
        
    @pytest.mark.asyncio
    async def test_backfill_empty_guilds(self, conversation_ai):
        """Test backfill with no guilds/channels"""
        # Mock empty bot guilds
        conversation_ai.bot.guilds = []
        
        # Run backfill
        await conversation_ai._backfill_message_history()
        
        # Should complete successfully even with no channels
        assert conversation_ai.history_backfilled == True
        assert len(conversation_ai.recent_messages) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 