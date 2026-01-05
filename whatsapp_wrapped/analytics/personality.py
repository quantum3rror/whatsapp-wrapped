"""
Personality classification module for WhatsApp Wrapped.
Classifies users based on their messaging patterns.
"""

def classify_personality(stats):
    """
    Classify user messaging personality based on patterns.

    Args:
        stats (dict): Statistics dictionary containing message data

    Returns:
        dict: Dictionary with 'personality' and 'description' keys
    """
    total = stats.get('total_messages', 0)
    sent = stats.get('sent', 0)
    received = stats.get('received', 0)

    # Avoid division by zero
    if total == 0:
        return {
            'personality': 'New Chatter',
            'description': 'Your WhatsApp journey is just beginning!'
        }

    # Calculate ratios
    sent_ratio = sent / total

    # Get peak hour
    top_hours = stats.get('top_hours', [])
    if top_hours and len(top_hours) > 0:
        peak_hour = top_hours[0]['hour']
    else:
        peak_hour = 12

    # Classify based on patterns
    if sent_ratio > 0.6:
        personality = "Conversationalist"
        description = "You love keeping the conversation going! You send more messages than you receive."
    elif sent_ratio < 0.4:
        personality = "Great Listener"
        description = "You're a thoughtful responder who takes time to listen before speaking."
    elif peak_hour >= 22 or peak_hour <= 5:
        personality = "Night Owl"
        description = "Your best conversations happen when most people are asleep."
    elif peak_hour >= 6 and peak_hour <= 9:
        personality = "Early Bird"
        description = "You're chatting before most people have their morning coffee."
    else:
        personality = "Balanced Chatter"
        description = "You maintain a perfect balance between talking and listening."

    return {
        'personality': personality,
        'description': description
    }
