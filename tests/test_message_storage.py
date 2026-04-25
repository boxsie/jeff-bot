import pytest
from conftest import MockDiscordMessage, MockDiscordUser


class TestMessageStorage:
    """Test message storage functionality"""
    
    def test_store_message_in_history_basic(self, conversation_ai, sample_user, sample_channel):
        """Test basic message storage"""
        message = MockDiscordMessage("Hello world!", sample_user, sample_channel)
        
        # Store message
        conversation_ai._store_message_in_history(message)
        
        # Check it was stored
        assert sample_channel.id in conversation_ai.recent_messages
        stored_messages = list(conversation_ai.recent_messages[sample_channel.id])
        assert len(stored_messages) == 1
        
        stored_msg = stored_messages[0]
        assert stored_msg['content'] == "Hello world!"
        assert stored_msg['author_id'] == sample_user.id
        assert stored_msg['author_name'] == sample_user.display_name
        assert stored_msg['message_id'] == message.id
        assert stored_msg['is_bot'] == False
        assert stored_msg['channel_name'] == "DM"  # No guild means DM
        assert stored_msg['guild_name'] is None  # No guild in this test
        assert 'timestamp' in stored_msg
        
    def test_store_message_in_history_with_guild(self, conversation_ai, sample_user, sample_channel, sample_guild):
        """Test message storage with guild context"""
        message = MockDiscordMessage("Guild message", sample_user, sample_channel, sample_guild)
        
        conversation_ai._store_message_in_history(message)
        
        stored_messages = list(conversation_ai.recent_messages[sample_channel.id])
        stored_msg = stored_messages[0]
        
        assert stored_msg['guild_name'] == sample_guild.name
        assert stored_msg['channel_name'] == sample_channel.name
        
    def test_store_bot_messages(self, conversation_ai, sample_channel):
        """Test that bot messages are stored"""
        bot_user = MockDiscordUser(99999, "TestBot")
        bot_user.bot = True
        
        message = MockDiscordMessage("Bot response", bot_user, sample_channel)
        conversation_ai._store_message_in_history(message)
        
        stored_messages = list(conversation_ai.recent_messages[sample_channel.id])
        assert len(stored_messages) == 1
        assert stored_messages[0]['is_bot'] == True
        assert stored_messages[0]['content'] == "Bot response"
        
    def test_store_command_messages(self, conversation_ai, sample_user, sample_channel):
        """Test that command messages are stored"""
        command_message = MockDiscordMessage("!help me", sample_user, sample_channel)
        conversation_ai._store_message_in_history(command_message)
        
        stored_messages = list(conversation_ai.recent_messages[sample_channel.id])
        assert len(stored_messages) == 1
        assert stored_messages[0]['content'] == "!help me"
        
    def test_message_limit_enforcement(self, conversation_ai, sample_user, sample_channel):
        """Test that only 50 messages are kept per channel"""
        # Add 60 messages to test the 50-message limit
        for i in range(60):
            message = MockDiscordMessage(f"Message {i}", sample_user, sample_channel)
            conversation_ai._store_message_in_history(message)
        
        # Should only have 50 messages
        stored_messages = list(conversation_ai.recent_messages[sample_channel.id])
        assert len(stored_messages) == 50
        
        # Should have the last 50 messages (10-59)
        contents = [msg['content'] for msg in stored_messages]
        assert "Message 10" in contents  # First message kept
        assert "Message 59" in contents  # Last message kept
        assert "Message 0" not in contents  # First messages should be gone
        assert "Message 9" not in contents
        
    def test_channel_isolation(self, conversation_ai, sample_user):
        """Test that messages are isolated per channel"""
        from conftest import MockDiscordChannel
        
        channel1 = MockDiscordChannel(11111, "general")
        channel2 = MockDiscordChannel(22222, "random")
        
        message1 = MockDiscordMessage("Message in general", sample_user, channel1)
        message2 = MockDiscordMessage("Message in random", sample_user, channel2)
        
        conversation_ai._store_message_in_history(message1)
        conversation_ai._store_message_in_history(message2)
        
        # Each channel should have its own messages
        assert len(conversation_ai.recent_messages[channel1.id]) == 1
        assert len(conversation_ai.recent_messages[channel2.id]) == 1
        
        assert conversation_ai.recent_messages[channel1.id][0]['content'] == "Message in general"
        assert conversation_ai.recent_messages[channel2.id][0]['content'] == "Message in random"
        
    def test_get_recent_messages(self, conversation_ai, sample_user, sample_channel):
        """Test retrieving recent messages"""
        # Add some messages
        for i in range(5):
            message = MockDiscordMessage(f"Message {i}", sample_user, sample_channel)
            conversation_ai._store_message_in_history(message)
        
        # Test getting all messages
        all_messages = conversation_ai.get_recent_messages(sample_channel.id)
        assert len(all_messages) == 5
        
        # Test getting limited messages
        limited_messages = conversation_ai.get_recent_messages(sample_channel.id, limit=3)
        assert len(limited_messages) == 3
        
        # Should get the last 3 messages
        contents = [msg['content'] for msg in limited_messages]
        assert "Message 2" in contents
        assert "Message 3" in contents
        assert "Message 4" in contents
        assert "Message 0" not in contents
        assert "Message 1" not in contents
        
    def test_get_recent_messages_empty_channel(self, conversation_ai):
        """Test getting messages from channel with no history"""
        messages = conversation_ai.get_recent_messages(99999)  # Non-existent channel
        assert messages == []
        
    def test_multiple_users_same_channel(self, conversation_ai, sample_channel):
        """Test storing messages from multiple users in same channel"""
        user1 = MockDiscordUser(1001, "User1")
        user2 = MockDiscordUser(1002, "User2")
        user3 = MockDiscordUser(1003, "User3")
        
        # Add messages from different users
        message1 = MockDiscordMessage("Hello from user1", user1, sample_channel)
        message2 = MockDiscordMessage("Hello from user2", user2, sample_channel)
        message3 = MockDiscordMessage("Hello from user3", user3, sample_channel)
        
        conversation_ai._store_message_in_history(message1)
        conversation_ai._store_message_in_history(message2)
        conversation_ai._store_message_in_history(message3)
        
        stored_messages = conversation_ai.get_recent_messages(sample_channel.id)
        assert len(stored_messages) == 3
        
        # Check different users are represented
        author_names = [msg['author_name'] for msg in stored_messages]
        assert "User1" in author_names
        assert "User2" in author_names
        assert "User3" in author_names
        
    def test_dm_channel_storage(self, conversation_ai, sample_user):
        """Test storing messages in DM channels"""
        from conftest import MockDiscordChannel
        
        # DM channel (no guild)
        dm_channel = MockDiscordChannel(88888, "DM")
        message = MockDiscordMessage("DM message", sample_user, dm_channel, None)
        
        conversation_ai._store_message_in_history(message)
        
        stored_messages = conversation_ai.get_recent_messages(dm_channel.id)
        assert len(stored_messages) == 1
        assert stored_messages[0]['channel_name'] == "DM"
        assert stored_messages[0]['guild_name'] is None
        
    def test_message_storage_with_special_characters(self, conversation_ai, sample_user, sample_channel):
        """Test storing messages with special characters and emojis"""
        special_message = MockDiscordMessage("Hello! 🎉 This has émojis and spéciál characters & symbols #test", sample_user, sample_channel)
        
        conversation_ai._store_message_in_history(special_message)
        
        stored_messages = conversation_ai.get_recent_messages(sample_channel.id)
        assert len(stored_messages) == 1
        assert stored_messages[0]['content'] == "Hello! 🎉 This has émojis and spéciál characters & symbols #test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 