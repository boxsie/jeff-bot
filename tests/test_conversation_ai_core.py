import pytest
from datetime import datetime
from unittest.mock import patch

from conftest import MockDiscordMessage


class TestConversationAI:
    """Test suite for ConversationAI cog core functionality"""
    
    def test_initialization(self, mock_bot, mock_ollama, mock_memory_repo):
        """Test cog initialization"""
        from cogs.conversation_ai import ConversationAI
        cog = ConversationAI(mock_bot, mock_ollama, mock_memory_repo)
        
        assert cog.bot == mock_bot
        assert cog.ollama == mock_ollama
        assert cog.memory_repo == mock_memory_repo
        assert isinstance(cog.user_memories, dict)
        assert isinstance(cog.general_insights, dict)
        assert isinstance(cog.ignored_channels, set)
        assert cog.bot_mentions_detected == 0
        assert cog.history_backfilled == False
        
    def test_should_process_message_valid(self, conversation_ai, sample_user, sample_channel):
        """Test message processing filter - valid messages"""
        # Valid message
        message = MockDiscordMessage("Hello, how are you today?", sample_user, sample_channel)
        assert conversation_ai._should_process_message(message) == True
        
        # Long enough message
        message = MockDiscordMessage("This is a test message", sample_user, sample_channel)
        assert conversation_ai._should_process_message(message) == True
        
    def test_should_process_message_invalid(self, conversation_ai, sample_user, sample_channel):
        """Test message processing filter - invalid messages"""
        from conftest import MockDiscordUser
        
        # Bot message
        bot_user = MockDiscordUser(12345, "BotUser")
        bot_user.bot = True
        message = MockDiscordMessage("Bot message", bot_user, sample_channel)
        assert conversation_ai._should_process_message(message) == False
        
        # Too short message
        message = MockDiscordMessage("hi", sample_user, sample_channel)
        assert conversation_ai._should_process_message(message) == False
        
        # Command messages
        command_messages = ["!help", "/command", "$test", "?query", ".info"]
        for cmd in command_messages:
            message = MockDiscordMessage(cmd, sample_user, sample_channel)
            assert conversation_ai._should_process_message(message) == False
            
    def test_should_process_message_ignored_channel(self, conversation_ai, sample_user, sample_channel, sample_guild):
        """Test message processing with ignored channels"""
        # Add channel to ignored list
        conversation_ai.ignored_channels.add(sample_channel.id)
        
        message = MockDiscordMessage("This should be ignored", sample_user, sample_channel, sample_guild)
        assert conversation_ai._should_process_message(message) == False
        
    @pytest.mark.asyncio
    async def test_process_message_for_memory_basic(self, conversation_ai, mock_ollama, sample_user, sample_channel):
        """Test basic message processing for memory extraction"""
        from conftest import MockDiscordGuild
        
        # Set up LLM response
        expected_metadata = {
            "metadata": {
                "topics": ["greeting", "casual"],
                "is_notable": False,
                "notable_reason": "",
                "user_insights": ["friendly person"],
                "sentiment": "positive",
                "contains_personal_info": False,
                "directed_at_bot_probability": 0.0,
                "bot_direction_reason": "Not directed at bot"
            }
        }
        
        message_content = mock_ollama._build_context_string(
            sample_user.display_name, "Hello everyone!", 
            channel_name=sample_channel.name, server_name="Test Server"
        )
        mock_ollama.set_response(message_content, expected_metadata)
        
        # Create message and process (with guild to match the expected context)
        sample_guild = MockDiscordGuild(22222, "Test Server")
        message = MockDiscordMessage("Hello everyone!", sample_user, sample_channel, sample_guild)
        await conversation_ai._process_message_for_memory(message)
        
        # Check user memory was created
        assert sample_user.id in conversation_ai.user_memories
        memory = conversation_ai.user_memories[sample_user.id]
        
        assert memory['user_name'] == sample_user.display_name
        assert memory['interaction_count'] == 1
        assert "greeting" in memory['topics_discussed']
        assert "casual" in memory['topics_discussed']
        assert "friendly person" in memory['personality_notes']
        assert len(memory['sentiment_history']) == 1
        assert memory['sentiment_history'][0]['sentiment'] == "positive"
        
    @pytest.mark.asyncio
    async def test_process_notable_interaction(self, conversation_ai, mock_ollama, sample_user, sample_channel):
        """Test processing of notable interactions"""
        from conftest import MockDiscordGuild
        
        # Set up LLM response for notable interaction
        expected_metadata = {
            "metadata": {
                "topics": ["personal", "family"],
                "is_notable": True,
                "notable_reason": "Sharing personal family information",
                "user_insights": ["has younger siblings", "family-oriented"],
                "sentiment": "positive",
                "contains_personal_info": True,
                "directed_at_bot_probability": 0.0,
                "bot_direction_reason": "Not directed at bot"
            }
        }
        
        sample_guild = MockDiscordGuild(22222, "Test Server")
        message = MockDiscordMessage("My little sister just graduated from college!", sample_user, sample_channel, sample_guild)
        message_content = mock_ollama._build_context_string(
            sample_user.display_name, message.content,
            channel_name=sample_channel.name, server_name="Test Server"
        )
        mock_ollama.set_response(message_content, expected_metadata)
        
        await conversation_ai._process_message_for_memory(message)
        
        # Check notable interaction was saved
        memory = conversation_ai.user_memories[sample_user.id]
        assert len(memory['notable_interactions']) == 1
        
        notable = memory['notable_interactions'][0]
        assert notable['reason'] == "Sharing personal family information"
        assert notable['sentiment'] == "positive"
        assert "personal" in notable['topics']
        assert "family" in notable['topics']
        
    @pytest.mark.asyncio
    async def test_multiple_interactions(self, conversation_ai, mock_ollama, sample_user, sample_channel):
        """Test multiple interactions build up memory correctly"""
        from conftest import MockDiscordGuild
        
        # First interaction
        message1_content = mock_ollama._build_context_string(
            sample_user.display_name, "I love playing guitar",
            channel_name=sample_channel.name, server_name="Test Server"
        )
        mock_ollama.set_response(
            message1_content,
            {
                "metadata": {
                    "topics": ["music", "guitar"],
                    "is_notable": False,
                    "user_insights": ["musician", "plays guitar"],
                    "sentiment": "positive",
                    "contains_personal_info": True,
                    "directed_at_bot_probability": 0.0,
                    "bot_direction_reason": "Not directed at bot"
                }
            }
        )
        
        sample_guild = MockDiscordGuild(22222, "Test Server")
        message1 = MockDiscordMessage("I love playing guitar", sample_user, sample_channel, sample_guild)
        await conversation_ai._process_message_for_memory(message1)
        
        # Second interaction  
        message2_content = mock_ollama._build_context_string(
            sample_user.display_name, "Going to a concert tonight!",
            channel_name=sample_channel.name, server_name="Test Server",
            conversation_history=[{"timestamp": "2025-01-01T10:00:00", "author_name": sample_user.display_name, "content": "I love playing guitar"}]
        )
        mock_ollama.set_response(
            message2_content,
            {
                "metadata": {
                    "topics": ["music", "concert", "events"],
                    "is_notable": True,
                    "notable_reason": "Sharing plans and interests",
                    "user_insights": ["enjoys live music", "active social life"],
                    "sentiment": "excited",
                    "contains_personal_info": True,
                    "directed_at_bot_probability": 0.0,
                    "bot_direction_reason": "Not directed at bot"
                }
            }
        )
        
        message2 = MockDiscordMessage("Going to a concert tonight!", sample_user, sample_channel, sample_guild)
        await conversation_ai._process_message_for_memory(message2)
        
        # Check accumulated memory
        memory = conversation_ai.user_memories[sample_user.id]
        assert memory['interaction_count'] == 2
        
        # Check topics accumulation
        topics = memory['topics_discussed']
        assert "music" in topics
        assert "guitar" in topics
        assert "concert" in topics
        assert "events" in topics
        
        # Check personality insights accumulation
        insights = memory['personality_notes']
        assert "musician" in insights
        assert "plays guitar" in insights
        assert "enjoys live music" in insights
        assert "active social life" in insights
        
        # Check sentiment history
        assert len(memory['sentiment_history']) == 2
        sentiments = [s['sentiment'] for s in memory['sentiment_history']]
        assert "positive" in sentiments
        assert "excited" in sentiments
        
        # Check notable interaction was saved
        assert len(memory['notable_interactions']) == 1
        
    @pytest.mark.asyncio
    async def test_memory_limits(self, conversation_ai, mock_ollama, sample_user, sample_channel):
        """Test that memory limits are enforced"""
        from conftest import MockDiscordGuild
        
        # Add many topics to test limit
        sample_guild = MockDiscordGuild(22222, "Test Server")
        for i in range(25):  # More than the 20 topic limit
            # For multiple messages, we need to account for conversation history building up
            conversation_history = None
            if i > 0:
                conversation_history = [{"timestamp": f"2025-01-01T10:0{min(i-1, 9)}:00", "author_name": sample_user.display_name, "content": f"Topic {max(0, i-1)}"}]
            
            context = mock_ollama._build_context_string(
                sample_user.display_name, f"Topic {i}",
                channel_name=sample_channel.name, server_name="Test Server",
                conversation_history=conversation_history
            )
            
            mock_ollama.set_response(
                context,
                {
                    "metadata": {
                        "topics": [f"topic_{i}"],
                        "is_notable": False,
                        "user_insights": [f"insight_{i}"],
                        "sentiment": "neutral",
                        "contains_personal_info": False,
                        "directed_at_bot_probability": 0.0,
                        "bot_direction_reason": "Not directed at bot"
                    }
                }
            )
            
            message = MockDiscordMessage(f"Topic {i}", sample_user, sample_channel, sample_guild)
            await conversation_ai._process_message_for_memory(message)
        
        memory = conversation_ai.user_memories[sample_user.id]
        
        # Check limits are enforced
        assert len(memory['topics_discussed']) <= 20
        assert len(memory['personality_notes']) <= 15
        assert len(memory['sentiment_history']) <= 10
        
        # Check most recent items are kept
        assert "topic_24" in memory['topics_discussed']
        assert "topic_0" not in memory['topics_discussed']
        
    @pytest.mark.asyncio
    async def test_llm_error_handling(self, conversation_ai, mock_ollama, sample_user, sample_channel):
        """Test handling of LLM errors"""
        from conftest import MockDiscordGuild
        
        # Set up LLM to return invalid response
        message_content = mock_ollama._build_context_string(
            sample_user.display_name, "Test message",
            channel_name=sample_channel.name, server_name="Test Server"
        )
        mock_ollama.set_response(
            message_content,
            None  # Invalid response
        )
        
        sample_guild = MockDiscordGuild(22222, "Test Server")
        message = MockDiscordMessage("Test message", sample_user, sample_channel, sample_guild)
        
        # Should not raise exception
        await conversation_ai._process_message_for_memory(message)
        
        # User memory should still be initialized
        assert sample_user.id in conversation_ai.user_memories
        memory = conversation_ai.user_memories[sample_user.id]
        assert memory['interaction_count'] == 0  # No increment due to error
        
    @pytest.mark.asyncio 
    async def test_guild_vs_dm_context(self, conversation_ai, mock_ollama, sample_user, sample_channel, sample_guild):
        """Test that guild and DM contexts are handled differently"""
        # Guild message
        guild_message = MockDiscordMessage("Guild message", sample_user, sample_channel, sample_guild)
        expected_guild_context = mock_ollama._build_context_string(
            sample_user.display_name, "Guild message",
            channel_name=sample_channel.name, server_name=sample_guild.name
        )
        
        mock_ollama.set_response(expected_guild_context, {
            "metadata": {
                "topics": ["guild"],
                "is_notable": False,
                "user_insights": ["guild user"],
                "sentiment": "neutral",
                "contains_personal_info": False
            }
        })
        
        await conversation_ai._process_message_for_memory(guild_message)
        
        # DM message (no guild)
        dm_message = MockDiscordMessage("DM message", sample_user, sample_channel, None)
        expected_dm_context = mock_ollama._build_context_string(
            sample_user.display_name, "DM message", is_dm=True
        )
        
        mock_ollama.set_response(expected_dm_context, {
            "metadata": {
                "topics": ["dm"],
                "is_notable": False,
                "user_insights": ["dm user"],
                "sentiment": "neutral",
                "contains_personal_info": False
            }
        })
        
        await conversation_ai._process_message_for_memory(dm_message)
        
        # Both should be processed but with different contexts
        memory = conversation_ai.user_memories[sample_user.id]
        assert "guild" in memory['topics_discussed']
        assert "dm" in memory['topics_discussed']
        
    def test_memory_initialization(self, conversation_ai, sample_user):
        """Test user memory initialization"""
        user_id = sample_user.id
        
        # Memory should not exist initially
        assert user_id not in conversation_ai.user_memories
        
        # Initialize memory structure
        conversation_ai.user_memories[user_id] = {
            'user_name': sample_user.display_name,
            'first_seen': datetime.now().isoformat(),
            'last_interaction': datetime.now().isoformat(),
            'interaction_count': 0,
            'topics_discussed': [],
            'notable_interactions': [],
            'personality_notes': [],
            'preferences': {},
            'sentiment_history': []
        }
        
        memory = conversation_ai.user_memories[user_id]
        assert memory['user_name'] == sample_user.display_name
        assert memory['interaction_count'] == 0
        assert isinstance(memory['topics_discussed'], list)
        assert isinstance(memory['notable_interactions'], list)
        assert isinstance(memory['personality_notes'], list)
        assert isinstance(memory['sentiment_history'], list)
        
    @pytest.mark.asyncio
    async def test_sentiment_tracking(self, conversation_ai, mock_ollama, sample_user, sample_channel):
        """Test sentiment tracking across interactions"""
        from conftest import MockDiscordGuild
        
        sentiments = ["positive", "negative", "neutral", "excited", "sad"]
        sample_guild = MockDiscordGuild(22222, "Test Server")
        
        for i, sentiment in enumerate(sentiments):
            # For multiple messages, account for conversation history
            conversation_history = None
            if i > 0:
                conversation_history = [{"timestamp": f"2025-01-01T10:0{min(i-1, 9)}:00", "author_name": sample_user.display_name, "content": f"Message {max(0, i-1)}"}]
            
            context = mock_ollama._build_context_string(
                sample_user.display_name, f"Message {i}",
                channel_name=sample_channel.name, server_name="Test Server",
                conversation_history=conversation_history
            )
            
            mock_ollama.set_response(
                context,
                {
                    "metadata": {
                        "topics": [f"topic_{i}"],
                        "is_notable": False,
                        "user_insights": [f"insight_{i}"],
                        "sentiment": sentiment,
                        "contains_personal_info": False,
                        "directed_at_bot_probability": 0.0,
                        "bot_direction_reason": "Not directed at bot"
                    }
                }
            )
            
            message = MockDiscordMessage(f"Message {i}", sample_user, sample_channel, sample_guild)
            await conversation_ai._process_message_for_memory(message)
        
        memory = conversation_ai.user_memories[sample_user.id]
        sentiment_history = memory['sentiment_history']
        
        assert len(sentiment_history) == 5
        recorded_sentiments = [s['sentiment'] for s in sentiment_history]
        assert recorded_sentiments == sentiments
        
        # Each entry should have timestamp
        for entry in sentiment_history:
            assert 'timestamp' in entry
            assert 'sentiment' in entry
            
    @pytest.mark.asyncio
    async def test_bot_direction_detection(self, conversation_ai, mock_ollama, sample_user, sample_channel):
        """Test detection of messages directed at the bot"""
        from conftest import MockDiscordGuild
        
        # Test high probability bot mention
        message1_content = mock_ollama._build_context_string(
            sample_user.display_name, "Hey bot, can you help me?",
            channel_name=sample_channel.name, server_name="Test Server"
        )
        mock_ollama.set_response(
            message1_content,
            {
                "metadata": {
                    "topics": ["help", "bot"],
                    "is_notable": False,
                    "user_insights": ["asking for help"],
                    "sentiment": "neutral",
                    "contains_personal_info": False,
                    "directed_at_bot_probability": 0.9,
                    "bot_direction_reason": "Direct address to bot with question"
                }
            }
        )
        
        sample_guild = MockDiscordGuild(22222, "Test Server")
        message = MockDiscordMessage("Hey bot, can you help me?", sample_user, sample_channel, sample_guild)
        
        initial_count = conversation_ai.bot_mentions_detected
        await conversation_ai._process_message_for_memory(message)
        
        # Should increment bot mentions counter
        assert conversation_ai.bot_mentions_detected == initial_count + 1
        
        # Test low probability (not directed at bot) - this will have conversation history from previous message
        message2_content = mock_ollama._build_context_string(
            sample_user.display_name, "I love pizza",
            channel_name=sample_channel.name, server_name="Test Server",
            conversation_history=[{"timestamp": "2025-01-01T10:00:00", "author_name": sample_user.display_name, "content": "Hey bot, can you help me?"}]
        )
        mock_ollama.set_response(
            message2_content,
            {
                "metadata": {
                    "topics": ["food", "pizza"],
                    "is_notable": False,
                    "user_insights": ["likes pizza"],
                    "sentiment": "positive",
                    "contains_personal_info": True,
                    "directed_at_bot_probability": 0.1,
                    "bot_direction_reason": "Casual conversation not directed at bot"
                }
            }
        )
        
        message2 = MockDiscordMessage("I love pizza", sample_user, sample_channel, sample_guild)
        await conversation_ai._process_message_for_memory(message2)
        
        # Should not increment bot mentions counter (probability too low)
        assert conversation_ai.bot_mentions_detected == initial_count + 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 