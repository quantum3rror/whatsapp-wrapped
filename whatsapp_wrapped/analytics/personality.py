"""
Personality classification module for WhatsApp Wrapped.
Classifies users based on their messaging patterns.
Returns 1 primary personality + 2 secondary traits.
"""

def classify_personality(stats):
    """
    Classify user messaging personality based on patterns.

    Args:
        stats (dict): Statistics dictionary containing message data

    Returns:
        dict: Dictionary with 'personality', 'description', and 'traits' keys
    """
    total = stats.get('total_messages', 0)
    sent = stats.get('sent', 0)
    received = stats.get('received', 0)

    # Avoid division by zero
    if total == 0:
        return {
            'personality': 'New Chatter',
            'description': 'Your WhatsApp journey is just beginning!',
            'traits': []
        }

    # Calculate base metrics
    sent_ratio = sent / total

    # Get peak hour
    top_hours = stats.get('top_hours', [])
    peak_hour = top_hours[0]['hour'] if top_hours else 12

    # Get response time data
    response_time = stats.get('response_time', {})
    median_seconds = response_time.get('median_seconds', 0) if response_time else 0

    # Get media counts for calculating percentages
    media_counts = stats.get('media_counts', [])
    media_dict = {m['type']: m['count'] for m in media_counts}

    # Calculate emoji percentage
    top_emojis = stats.get('top_emojis', [])
    total_emoji_count = sum(e['count'] for e in top_emojis) if top_emojis else 0
    emoji_pct = (total_emoji_count / total * 100) if total > 0 else 0

    # Calculate sticker percentage
    stickers_count = media_dict.get('Stickers', 0)
    sticker_pct = (stickers_count / total * 100) if total > 0 else 0

    # Calculate audio/voice note percentage
    audio_count = media_dict.get('Audio', 0)
    audio_pct = (audio_count / total * 100) if total > 0 else 0

    # Calculate scores for each personality (0-100)
    scores = {}

    # Conversationalist: High sent ratio
    if sent_ratio > 0.6:
        scores['Conversationalist'] = 70 + int((sent_ratio - 0.6) * 50)
    elif sent_ratio > 0.5:
        scores['Conversationalist'] = 50 + int((sent_ratio - 0.5) * 200)
    else:
        scores['Conversationalist'] = 0

    # Great Listener: Low sent ratio
    if sent_ratio < 0.4:
        scores['Great Listener'] = 70 + int((0.4 - sent_ratio) * 50)
    elif sent_ratio < 0.5:
        scores['Great Listener'] = 50 + int((0.5 - sent_ratio) * 200)
    else:
        scores['Great Listener'] = 0

    # Night Owl: Peak hours 22-5
    if peak_hour >= 22 or peak_hour <= 5:
        scores['Night Owl'] = 60  # Always if peak hour is late night
    elif peak_hour >= 20 or peak_hour <= 6:
        scores['Night Owl'] = 30  # Partial match
    else:
        scores['Night Owl'] = 0

    # Early Bird: Peak hours 6-9
    if peak_hour >= 6 and peak_hour <= 9:
        scores['Early Bird'] = 60
    elif peak_hour >= 5 and peak_hour <= 10:
        scores['Early Bird'] = 30
    else:
        scores['Early Bird'] = 0

    # Balanced Chatter: Mid-range sent ratio and normal hours
    if 0.4 <= sent_ratio <= 0.6 and 10 <= peak_hour <= 21:
        scores['Balanced Chatter'] = 50
    elif 0.35 <= sent_ratio <= 0.65:
        scores['Balanced Chatter'] = 25
    else:
        scores['Balanced Chatter'] = 0

    # Quick Responder: Fast median response time
    if median_seconds > 0 and median_seconds < 60:
        scores['Quick Responder'] = 65
    elif median_seconds > 0 and median_seconds < 120:
        scores['Quick Responder'] = 45
    elif median_seconds > 0 and median_seconds < 300:
        scores['Quick Responder'] = 25
    else:
        scores['Quick Responder'] = 0

    # Thoughtful Replier: Slow median response time
    if median_seconds > 1800:  # 30 minutes
        scores['Thoughtful Replier'] = 65
    elif median_seconds > 900:  # 15 minutes
        scores['Thoughtful Replier'] = 45
    elif median_seconds > 300:  # 5 minutes
        scores['Thoughtful Replier'] = 25
    else:
        scores['Thoughtful Replier'] = 0

    # Emoji Enthusiast: High emoji usage
    if emoji_pct > 15:
        scores['Emoji Enthusiast'] = 55
    elif emoji_pct > 8:
        scores['Emoji Enthusiast'] = 35
    elif emoji_pct > 3:
        scores['Emoji Enthusiast'] = 15
    else:
        scores['Emoji Enthusiast'] = 0

    # Sticker Fanatic: High sticker usage
    if sticker_pct > 5:
        scores['Sticker Fanatic'] = 50
    elif sticker_pct > 2:
        scores['Sticker Fanatic'] = 30
    elif sticker_pct > 1:
        scores['Sticker Fanatic'] = 15
    else:
        scores['Sticker Fanatic'] = 0

    # Voice Note Lover: High audio usage
    if audio_pct > 5:
        scores['Voice Note Lover'] = 50
    elif audio_pct > 2:
        scores['Voice Note Lover'] = 30
    elif audio_pct > 1:
        scores['Voice Note Lover'] = 15
    else:
        scores['Voice Note Lover'] = 0

    # Personality definitions
    personalities = {
        'Conversationalist': "You love keeping the conversation going! You send more messages than you receive.",
        'Great Listener': "You're a thoughtful responder who takes time to listen before speaking.",
        'Night Owl': "Your best conversations happen when most people are asleep.",
        'Early Bird': "You're chatting before most people have their morning coffee.",
        'Balanced Chatter': "You maintain a perfect balance between talking and listening.",
        'Quick Responder': "You're always on it! Replies fly from your thumbs in under a minute.",
        'Thoughtful Replier': "You take your time to craft meaningful responses.",
        'Emoji Enthusiast': "You express yourself in color and emotions! 🎨",
        'Sticker Fanatic': "Why type when you can sticker? Your conversations are an art gallery.",
        'Voice Note Lover': "You'd rather talk than type. Your voice notes are legendary."
    }

    # Sort by score (highest first)
    sorted_personalities = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Filter out zero scores
    nonzero_personalities = [(name, score) for name, score in sorted_personalities if score > 0]

    # If no personalities matched (rare edge case), default to Balanced Chatter
    if not nonzero_personalities:
        return {
            'personality': 'Balanced Chatter',
            'description': personalities['Balanced Chatter'],
            'traits': []
        }

    # Primary = top score
    primary_name, primary_score = nonzero_personalities[0]

    # Traits = next 2 highest
    traits = [name for name, _ in nonzero_personalities[1:3]]

    return {
        'personality': primary_name,
        'description': personalities[primary_name],
        'traits': traits
    }
