#!/usr/bin/env python3
"""
WhatsApp Wrapped MVP - Simple script to analyze WhatsApp data from iOS backup
"""

import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
import json
import argparse
from jinja2 import Template

# Apple Core Data timestamp starts from 2001-01-01 instead of Unix epoch (1970-01-01)
APPLE_TIMESTAMP_OFFSET = 978307200

def find_ios_backups():
    """Find iOS backups on macOS"""
    backup_path = Path.home() / "Library" / "Application Support" / "MobileSync" / "Backup"

    if not backup_path.exists():
        print(f"❌ No iOS backups found at {backup_path}")
        return []

    try:
        backups = []
        for backup_dir in backup_path.iterdir():
            if backup_dir.is_dir():
                info_plist = backup_dir / "Info.plist"
                if info_plist.exists():
                    backups.append(backup_dir)
        return backups
    except PermissionError:
        print(f"❌ Permission denied accessing {backup_path}")
        print("\n💡 To fix this on macOS:")
        print("   1. Open System Preferences → Privacy & Security → Full Disk Access")
        print("   2. Add Terminal (or your terminal app)")
        print("   3. Restart Terminal and try again")
        print("\n💡 Alternative: Manually extract WhatsApp database")
        print("   Use a tool like iMazing or manually locate ChatStorage.sqlite")
        return []

def find_whatsapp_db(backup_path):
    """Find WhatsApp ChatStorage.sqlite in iOS backup"""
    # WhatsApp database hash for ChatStorage.sqlite
    # Domain: AppDomainGroup-group.net.whatsapp.WhatsApp.shared
    # File: ChatStorage.sqlite
    db_hash = "7c7fba66680ef796b916b067077cc246adacf01d"

    db_file = backup_path / db_hash
    if db_file.exists():
        return db_file

    # Also check in subfolders (some backup formats)
    for subdir in ["7c", "7c/7f"]:
        db_file = backup_path / subdir / db_hash
        if db_file.exists():
            return db_file

    return None

def apple_timestamp_to_datetime(apple_timestamp):
    """Convert Apple Core Data timestamp to datetime"""
    if apple_timestamp is None:
        return None
    unix_timestamp = apple_timestamp + APPLE_TIMESTAMP_OFFSET
    return datetime.fromtimestamp(unix_timestamp)

def get_year_timestamp_bounds(year):
    """Get Apple timestamp bounds for a given year"""
    # Start of year (Jan 1, 00:00:00)
    start_dt = datetime(year, 1, 1, 0, 0, 0)
    start_unix = int(start_dt.timestamp())
    start_apple = start_unix - APPLE_TIMESTAMP_OFFSET

    # End of year (Dec 31, 23:59:59)
    end_dt = datetime(year, 12, 31, 23, 59, 59)
    end_unix = int(end_dt.timestamp())
    end_apple = end_unix - APPLE_TIMESTAMP_OFFSET

    return start_apple, end_apple

def analyze_whatsapp_db(db_path, year=None):
    """Analyze WhatsApp database and extract statistics"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Set up date filtering
    if year and year > 0:
        start_ts, end_ts = get_year_timestamp_bounds(year)
        date_filter = f"AND ZMESSAGEDATE >= {start_ts} AND ZMESSAGEDATE <= {end_ts}"
        print(f"🗓️  Filtering for year: {year}\n")
    else:
        date_filter = ""
        year = None  # Ensure None for "all years"

    print("📊 Analyzing WhatsApp database...\n")

    # Get total message count
    cursor.execute(f"SELECT COUNT(*) FROM ZWAMESSAGE WHERE ZMESSAGEDATE IS NOT NULL {date_filter}")
    total_messages = cursor.fetchone()[0]
    print(f"✓ Total messages: {total_messages:,}")

    # Get date range
    cursor.execute("""
        SELECT MIN(ZMESSAGEDATE), MAX(ZMESSAGEDATE)
        FROM ZWAMESSAGE
        WHERE ZMESSAGEDATE IS NOT NULL
    """)
    min_date, max_date = cursor.fetchone()
    min_dt = apple_timestamp_to_datetime(min_date)
    max_dt = apple_timestamp_to_datetime(max_date)
    print(f"✓ Date range: {min_dt.date() if min_dt else 'N/A'} to {max_dt.date() if max_dt else 'N/A'}")

    # Sent vs received
    cursor.execute(f"""
        SELECT ZISFROMME, COUNT(*)
        FROM ZWAMESSAGE
        WHERE ZMESSAGEDATE IS NOT NULL {date_filter}
        GROUP BY ZISFROMME
    """)
    sent_received = dict(cursor.fetchall())
    received = sent_received.get(0, 0)
    sent = sent_received.get(1, 0)
    print(f"✓ Sent: {sent:,} | Received: {received:,}")

    # Total conversations
    cursor.execute(f"SELECT COUNT(DISTINCT ZCHATSESSION) FROM ZWAMESSAGE WHERE ZMESSAGEDATE IS NOT NULL {date_filter}")
    total_chats = cursor.fetchone()[0]
    print(f"✓ Total conversations: {total_chats}")

    # Top individual chats (ZSESSIONTYPE = 0 for private/individual)
    cursor.execute(f"""
        SELECT
            cs.ZPARTNERNAME,
            COUNT(*) as msg_count
        FROM ZWAMESSAGE m
        JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
        WHERE cs.ZPARTNERNAME IS NOT NULL
          AND m.ZMESSAGEDATE IS NOT NULL
          AND cs.ZSESSIONTYPE = 0
          {date_filter}
        GROUP BY cs.ZPARTNERNAME
        ORDER BY msg_count DESC
        LIMIT 10
    """)
    top_individual_chats = cursor.fetchall()

    print("\n🏆 Top 10 Individual Chats:")
    for i, (name, count) in enumerate(top_individual_chats, 1):
        print(f"  {i}. {name}: {count:,} messages")

    # Top group chats (ZSESSIONTYPE = 1 for groups)
    cursor.execute(f"""
        SELECT
            cs.ZPARTNERNAME,
            COUNT(*) as msg_count
        FROM ZWAMESSAGE m
        JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
        WHERE cs.ZPARTNERNAME IS NOT NULL
          AND m.ZMESSAGEDATE IS NOT NULL
          AND cs.ZSESSIONTYPE = 1
          {date_filter}
        GROUP BY cs.ZPARTNERNAME
        ORDER BY msg_count DESC
        LIMIT 10
    """)
    top_groups = cursor.fetchall()

    print("\n👥 Top 10 Group Chats:")
    for i, (name, count) in enumerate(top_groups, 1):
        print(f"  {i}. {name}: {count:,} messages")

    # Messages by hour
    cursor.execute(f"""
        SELECT
            CAST(strftime('%H', datetime(ZMESSAGEDATE + 978307200, 'unixepoch')) AS INTEGER) as hour,
            COUNT(*) as count
        FROM ZWAMESSAGE
        WHERE ZMESSAGEDATE IS NOT NULL {date_filter}
        GROUP BY hour
        ORDER BY count DESC
        LIMIT 5
    """)
    top_hours = cursor.fetchall()

    print("\n⏰ Top 5 Messaging Hours:")
    for hour, count in top_hours:
        print(f"  {hour:02d}:00 - {count:,} messages")

    # Messages by day of week
    cursor.execute(f"""
        SELECT
            CASE CAST(strftime('%w', datetime(ZMESSAGEDATE + 978307200, 'unixepoch')) AS INTEGER)
                WHEN 0 THEN 'Sunday'
                WHEN 1 THEN 'Monday'
                WHEN 2 THEN 'Tuesday'
                WHEN 3 THEN 'Wednesday'
                WHEN 4 THEN 'Thursday'
                WHEN 5 THEN 'Friday'
                WHEN 6 THEN 'Saturday'
            END as day_name,
            COUNT(*) as count
        FROM ZWAMESSAGE
        WHERE ZMESSAGEDATE IS NOT NULL {date_filter}
        GROUP BY day_name
        ORDER BY count DESC
    """)
    days = cursor.fetchall()

    print("\n📅 Messages by Day of Week:")
    for day, count in days:
        print(f"  {day}: {count:,} messages")

    # Prepare statistics for JSON output
    stats = {
        "year": year,
        "total_messages": total_messages,
        "sent": sent,
        "received": received,
        "total_conversations": total_chats,
        "date_range": {
            "start": str(min_dt.date()) if min_dt else None,
            "end": str(max_dt.date()) if max_dt else None
        },
        "top_individual_chats": [{"name": name, "count": count} for name, count in top_individual_chats],
        "top_groups": [{"name": name, "count": count} for name, count in top_groups],
        "top_hours": [{"hour": hour, "count": count} for hour, count in top_hours],
        "days_of_week": [{"day": day, "count": count} for day, count in days]
    }

    conn.close()
    return stats

def generate_html_wrapped(stats, output_file):
    """Generate HTML Wrapped visualization"""
    # Import personality classifier
    import sys
    from pathlib import Path

    # Add current directory to path to import personality module
    current_dir = Path(__file__).parent
    sys.path.insert(0, str(current_dir))

    from whatsapp_wrapped.analytics.personality import classify_personality

    # Add personality classification
    personality = classify_personality(stats)
    stats.update(personality)

    # Read template
    template_path = current_dir / 'whatsapp_wrapped' / 'templates' / 'wrapped.html'

    if not template_path.exists():
        print(f"⚠️  Template not found at {template_path}")
        print("   HTML generation skipped.")
        return

    with open(template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()

    # Prepare data for template
    year_display = stats['year'] if stats.get('year') else 'All Time'

    # Handle missing or empty top_individual_chats
    top_individual_chats = stats.get('top_individual_chats', [])
    if len(top_individual_chats) < 3:
        # Pad with empty entries if needed
        while len(top_individual_chats) < 3:
            top_individual_chats.append({'name': 'No data', 'count': 0})

    # Handle missing or empty top_groups
    top_groups = stats.get('top_groups', [])
    if len(top_groups) < 3:
        # Pad with empty entries if needed
        while len(top_groups) < 3:
            top_groups.append({'name': 'No data', 'count': 0})

    # Render template
    template = Template(template_content)
    html = template.render(
        year=year_display,
        total_messages=f"{stats['total_messages']:,}",
        sent=f"{stats['sent']:,}",
        received=f"{stats['received']:,}",
        top_individual_chats=top_individual_chats[:3],  # Top 3
        top_groups=top_groups[:3],  # Top 3
        total_conversations=stats['total_conversations'],
        date_range=stats.get('date_range', {}),
        personality=stats.get('personality', 'Chatter'),
        personality_description=stats.get('description', ''),
        data_json=json.dumps(stats)
    )

    # Write HTML file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

def main():
    parser = argparse.ArgumentParser(description='WhatsApp Wrapped MVP - Analyze your WhatsApp conversations')
    parser.add_argument('--db', type=str, help='Path to ChatStorage.sqlite file (if already extracted)')
    parser.add_argument('--output', type=str, default='whatsapp_wrapped_stats.json', help='Output JSON file')
    parser.add_argument('--year', type=int, default=2025, help='Year to analyze (default: 2025, use 0 for all years)')
    args = parser.parse_args()

    print("🎉 WhatsApp Wrapped MVP\n")
    print("=" * 50)

    # If user provided database path directly
    if args.db:
        db_path = Path(args.db)
        if not db_path.exists():
            print(f"❌ Database file not found: {db_path}")
            return
        print(f"✓ Using provided database: {db_path}")
        print(f"✓ Size: {db_path.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        # Find iOS backups
        print("\n[1/3] Finding iOS backups...")
        backups = find_ios_backups()

        if not backups:
            print("\n❌ No iOS backups found.")
            print("\n💡 You can also manually provide the database:")
            print(f"   python {sys.argv[0]} --db /path/to/ChatStorage.sqlite")
            return

        print(f"✓ Found {len(backups)} backup(s)")

        # Use the most recent backup
        backup_path = backups[0]
        print(f"✓ Using backup: {backup_path.name}")

        # Find WhatsApp database
        print("\n[2/3] Looking for WhatsApp database...")
        db_path = find_whatsapp_db(backup_path)

        if not db_path:
            print("❌ WhatsApp database not found in backup.")
            print("💡 Make sure you have WhatsApp installed and have created messages.")
            print(f"\n💡 Or provide the database manually:")
            print(f"   python {sys.argv[0]} --db /path/to/ChatStorage.sqlite")
            return

        print(f"✓ Found ChatStorage.sqlite ({db_path.stat().st_size / 1024 / 1024:.1f} MB)")

    # Analyze database
    print("\n[3/3] Analyzing your WhatsApp data...")
    print("=" * 50)

    try:
        stats = analyze_whatsapp_db(db_path, year=args.year)
    except Exception as e:
        print(f"\n❌ Error analyzing database: {e}")
        print("\n💡 Make sure the file is a valid WhatsApp ChatStorage.sqlite database")
        return

    # Save to JSON
    with open(args.output, 'w') as f:
        json.dump(stats, f, indent=2)

    # Generate HTML visualization
    html_output = args.output.replace('.json', '.html')
    try:
        generate_html_wrapped(stats, html_output)
        html_generated = True
    except Exception as e:
        print(f"\n⚠️  HTML generation failed: {e}")
        html_generated = False

    print("\n" + "=" * 50)
    year_msg = f" for {args.year}" if args.year and args.year > 0 else ""
    print(f"✅ Analysis complete{year_msg}!")
    print(f"📊 Statistics saved to: {args.output}")
    if html_generated:
        print(f"🎉 HTML visualization: {html_output}")
        print(f"\n💡 Open {html_output} in your browser to see your Wrapped!")
    print("\n🔒 Privacy: All data processed locally. Nothing sent anywhere.")

if __name__ == "__main__":
    main()
