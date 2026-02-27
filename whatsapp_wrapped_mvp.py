#!/usr/bin/env python3
"""
WhatsApp Wrapped MVP - Analyze WhatsApp conversations from iOS backups

Supported Platforms:
    - macOS (Darwin): ~/Library/Application Support/MobileSync/Backup
    - Windows: ~/Apple/MobileSync/Backup (Apple Devices app, formerly iTunes)
    - Linux: ~/.config/apple-mobile-sync/Backup

Permission Requirements (macOS):
    Terminal needs Full Disk Access to read iOS backups:
    1. System Settings → Privacy & Security → Full Disk Access
    2. Add your terminal app (Terminal, iTerm2, etc.)
    3. Restart terminal and try again

Usage Examples:
    python whatsapp_wrapped_mvp.py --list-backups              # List all backups
    python whatsapp_wrapped_mvp.py --year 2025                 # Analyze 2025
    python whatsapp_wrapped_mvp.py --db /path/to/ChatStorage.sqlite  # Use specific DB
"""

import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import json
import argparse
import platform
import re
from jinja2 import Template
import plistlib

# Regex for matching emoji characters (covers most common emoji Unicode ranges)
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # Emoticons
    "\U0001F300-\U0001F5FF"  # Misc symbols & pictographs
    "\U0001F680-\U0001F6FF"  # Transport & map
    "\U0001F1E0-\U0001F1FF"  # Flags
    "\U0001F900-\U0001F9FF"  # Supplemental symbols
    "\U0001FA00-\U0001FA6F"  # Chess symbols
    "\U0001FA70-\U0001FAFF"  # Symbols extended-A
    "\U00002702-\U000027B0"  # Dingbats
    "\U0000FE00-\U0000FE0F"  # Variation selectors
    "\U0000200D"             # Zero width joiner
    "\U000023E9-\U000023F3"  # Misc technical
    "\U000023F8-\U000023FA"
    "\U00002600-\U000026FF"  # Misc symbols
    "\U00002700-\U000027BF"  # Dingbats
    "\U00002934-\U00002935"
    "\U000025AA-\U000025FE"
    "\U00002B05-\U00002B07"
    "\U00002B1B-\U00002B1C"
    "\U00002B50"
    "\U00002B55"
    "\U00003030"
    "\U0000303D"
    "\U00003297"
    "\U00003299"
    "\U0000200D"             # ZWJ
    "\U0000FE0F"             # Variation selector
    "]+",
    flags=re.UNICODE
)

# Apple Core Data timestamp starts from 2001-01-01 instead of Unix epoch (1970-01-01)
APPLE_TIMESTAMP_OFFSET = 978307200

# iOS backup locations by platform
BACKUP_LOCATIONS = {
    'darwin': '~/Library/Application Support/MobileSync/Backup',
    'windows': '~/Apple/MobileSync/Backup',  # Apple Devices app
    'linux': '~/.config/apple-mobile-sync/Backup'
}

# Platform detection for Windows-specific timestamp handling
_IS_WINDOWS = platform.system() == 'Windows'

def get_backup_locations():
    """Get iOS backup locations for the current platform"""
    system = platform.system().lower()

    # Map platform.system() to our keys
    if system == 'darwin':
        return [Path.home() / "Library" / "Application Support" / "MobileSync" / "Backup"]
    elif system == 'windows':
        # Apple Devices app (formerly iTunes) uses ~/Apple/MobileSync/Backup
        return [Path.home() / "Apple" / "MobileSync" / "Backup"]
    elif system == 'linux':
        return [Path.home() / ".config" / "apple-mobile-sync" / "Backup"]
    else:
        return []

def get_platform_fix_instructions():
    """Get platform-specific instructions for fixing permission/access issues"""
    system = platform.system().lower()

    if system == 'darwin':
        return """
💡 To fix this on macOS:
   1. Open System Settings → Privacy & Security → Full Disk Access
   2. Add Terminal (or your terminal app, e.g., iTerm2)
   3. Restart Terminal and try again

💡 Alternative: Manually extract WhatsApp database
   Use a tool like iMazing, 3uTools, or iPhone Backup Extractor
   Then run with --db flag:
   python whatsapp_wrapped_mvp.py --db /path/to/ChatStorage.sqlite"""
    elif system == 'windows':
        return """
💡 To fix this on Windows:
   1. Open Apple Devices app (formerly iTunes)
   2. Verify your device has been backed up
   3. Check backup location: C:\\Users\\<YourName>\\Apple\\MobileSync\\Backup

💡 Alternative: Manually extract WhatsApp database
   Use a tool like iMazing or 3uTools
   Then run with --db flag:
   python whatsapp_wrapped_mvp.py --db C:\\path\\to\\ChatStorage.sqlite"""
    else:
        return """
💡 Alternative: Manually extract WhatsApp database
   Use a tool like iMazing or libimobiletools
   Then run with --db flag:
   python whatsapp_wrapped_mvp.py --db /path/to/ChatStorage.sqlite"""

def find_ios_backups(verbose=True):
    """Find iOS backups and return metadata (path, device name, date, last modified)"""
    locations = get_backup_locations()
    backups = []
    system = platform.system().lower()

    if not locations:
        if verbose:
            print(f"⚠️  Unsupported platform: {system}")
            print(f"💡 Use --db flag to provide ChatStorage.sqlite manually")
        return []

    for base_path in locations:
        base_path = base_path.expanduser()

        if not base_path.exists():
            continue

        try:
            for backup_dir in base_path.iterdir():
                if not backup_dir.is_dir():
                    continue

                # Try to get device info from Info.plist
                info_plist = backup_dir / "Info.plist"
                device_name = None
                backup_date = None

                if info_plist.exists():
                    try:
                        with open(info_plist, 'rb') as f:
                            plist_data = plistlib.load(f)
                            device_name = plist_data.get('Device Name', plist_data.get('Display Name', 'Unknown'))
                            # Get last backup date
                            backup_date = plist_data.get('Last Backup Date')
                    except Exception:
                        pass

                # Fallback to directory modification time
                if not backup_date:
                    try:
                        backup_date = datetime.fromtimestamp(backup_dir.stat().st_mtime)
                    except Exception:
                        backup_date = None

                # Check if this looks like a valid backup (has Manifest.plist or files)
                manifest = backup_dir / "Manifest.plist"
                status = "valid" if manifest.exists() else "incomplete"

                backups.append({
                    'path': backup_dir,
                    'device_name': device_name or backup_dir.name[:8],
                    'backup_date': backup_date,
                    'status': status,
                    'id': backup_dir.name
                })

        except PermissionError:
            if verbose:
                print(f"❌ Permission denied accessing {base_path}")
                print(get_platform_fix_instructions())
        except Exception as e:
            if verbose:
                print(f"⚠️  Error accessing {base_path}: {e}")

    # Sort by backup date (newest first)
    backups.sort(key=lambda b: b['backup_date'] or datetime.min, reverse=True)

    return backups

def list_backups():
    """List all discovered iOS backups with details"""
    backups = find_ios_backups(verbose=False)
    system = platform.system().lower()

    if not backups:
        print("❌ No iOS backups found")
        print(f"\nExpected location on {system.title()}:")
        for loc in get_backup_locations():
            print(f"  {loc.expanduser()}")
        print(get_platform_fix_instructions())
        return

    print(f"✅ Found {len(backups)} iOS backup(s):\n")

    for i, backup in enumerate(backups, 1):
        date_str = backup['backup_date'].strftime('%Y-%m-%d %H:%M') if backup['backup_date'] else 'Unknown'
        status_icon = "✓" if backup['status'] == "valid" else "⚠️"

        print(f"{status_icon} [{i}] {backup['device_name']}")
        print(f"     ID: {backup['id']}")
        print(f"     Date: {date_str}")
        print(f"     Path: {backup['path']}")
        if backup['status'] != "valid":
            print(f"     Status: {backup['status']} (may not contain all data)")
        print()

    # Show backup location
    print(f"Backups searched in:")
    for loc in get_backup_locations():
        print(f"  {loc.expanduser()}")

def find_whatsapp_db(backup_path, verbose=True):
    """Find WhatsApp ChatStorage.sqlite in iOS backup

    Searches multiple known hash patterns and locations.
    Returns (Path, description) or (None, None).
    """
    # Known WhatsApp database hashes for ChatStorage.sqlite
    # Different iOS versions/WhatsApp versions may use different hashes
    db_hashes = [
        "7c7fba66680ef796b916b067077cc246adacf01d",  # Common hash
        "a31097e8a08d1f86658ee3f0a81decb7f3c59837",  # Alternate hash
    ]

    # Also check for any file ending in .sqlite that might be the database
    potential_dbs = []

    # Try known hashes first (fast path)
    for db_hash in db_hashes:
        # Direct location
        db_file = backup_path / db_hash
        if db_file.exists():
            return db_file, "known hash"

        # Check in hash-prefixed subfolders (some backup formats)
        prefix = db_hash[:2]
        db_file = backup_path / prefix / db_hash
        if db_file.exists():
            return db_file, f"hash subfolder ({prefix})"

    # Thorough search - scan for any .sqlite or .db files
    if verbose:
        print("   Scanning backup directory for WhatsApp database...")

    try:
        # First check Manifest.plist to find file mapping
        manifest = backup_path / "Manifest.plist"
        if manifest.exists():
            try:
                with open(manifest, 'rb') as f:
                    manifest_data = plistlib.load(f)
                    # The manifest contains file metadata; we can check for WhatsApp files
                    if verbose:
                        print("   ✓ Found backup manifest")
            except Exception:
                pass

        # Search for SQLite files in the backup
        for item in backup_path.rglob("*.sqlite"):
            # Check if this might be a WhatsApp database
            # ChatStorage.sqlite or variations
            if any(name in str(item).lower() for name in ["chatstorage", "whatsapp", "7c7fba"]):
                return item, "filename match"

        # Also check for .db files
        for item in backup_path.rglob("*.db"):
            if "chatstorage" in str(item).lower() or "whatsapp" in str(item).lower():
                return item, "filename match (.db)"

        # Last resort: check all files for SQLite magic bytes
        for item in backup_path.rglob("*"):
            if item.is_file() and item.stat().st_size > 100:
                try:
                    with open(item, 'rb') as f:
                        header = f.read(16)
                        if header == b'SQLite format 3\x00':
                            # This is a SQLite database - might be WhatsApp
                            potential_dbs.append((item, "SQLite magic bytes"))
                except (PermissionError, IOError):
                    continue

        # Return the largest potential database
        if potential_dbs:
            potential_dbs.sort(key=lambda x: x[0].stat().st_size, reverse=True)
            if verbose:
                print(f"   Found {len(potential_dbs)} potential database(s)")
                for db, reason in potential_dbs[:3]:
                    size_mb = db.stat().st_size / 1024 / 1024
                    print(f"     - {db.name} ({size_mb:.1f} MB, {reason})")
            return potential_dbs[0]

    except (PermissionError, Exception) as e:
        if verbose:
            print(f"   ⚠️  Error scanning backup: {e}")

    return None, None

def _apple_timestamp_to_datetime_windows(apple_timestamp):
    """Windows: Use timedelta (fromtimestamp has limited range)"""
    if apple_timestamp is None:
        return None
    unix_timestamp = apple_timestamp + APPLE_TIMESTAMP_OFFSET
    return datetime(1970, 1, 1) + timedelta(seconds=unix_timestamp)

def _apple_timestamp_to_datetime_unix(apple_timestamp):
    """Unix (macOS/Linux): Use fromtimestamp (fully supported)"""
    if apple_timestamp is None:
        return None
    unix_timestamp = apple_timestamp + APPLE_TIMESTAMP_OFFSET
    return datetime.fromtimestamp(unix_timestamp)

def apple_timestamp_to_datetime(apple_timestamp):
    """Convert Apple Core Data timestamp to datetime (platform-aware)"""
    if _IS_WINDOWS:
        return _apple_timestamp_to_datetime_windows(apple_timestamp)
    return _apple_timestamp_to_datetime_unix(apple_timestamp)

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

    # Calculate days in analysis period
    if year and year > 0:
        period_start = datetime(year, 1, 1)
        period_end = min(datetime(year, 12, 31), datetime.now())
        days_in_period = max((period_end - period_start).days, 1)
    elif min_dt and max_dt:
        days_in_period = max((max_dt - min_dt).days, 1)
    else:
        days_in_period = 365

    messages_per_day = round(total_messages / days_in_period, 1)
    print(f"✓ Messages per day: {messages_per_day}")

    # Busiest single day
    cursor.execute(f"""
        SELECT
            date(ZMESSAGEDATE + 978307200, 'unixepoch') as msg_date,
            COUNT(*) as count
        FROM ZWAMESSAGE
        WHERE ZMESSAGEDATE IS NOT NULL {date_filter}
        GROUP BY msg_date
        ORDER BY count DESC
        LIMIT 1
    """)
    busiest_day_row = cursor.fetchone()
    if busiest_day_row:
        busiest_day_date, busiest_day_count = busiest_day_row
        print(f"\n🔥 Busiest day: {busiest_day_date} with {busiest_day_count:,} messages")
    else:
        busiest_day_date, busiest_day_count = None, 0

    # Top emojis from sent messages
    print("\n😂 Analyzing emojis...")
    cursor.execute(f"""
        SELECT ZTEXT
        FROM ZWAMESSAGE
        WHERE ZTEXT IS NOT NULL
          AND ZMESSAGEDATE IS NOT NULL
          AND ZISFROMME = 1
          {date_filter}
    """)
    emoji_counter = Counter()
    for (text,) in cursor:
        if text:
            # Find all emoji sequences, then split into individual emojis
            emojis = EMOJI_PATTERN.findall(text)
            for emoji_seq in emojis:
                # Split the sequence into individual grapheme clusters
                # Each emoji is typically 1-2 codepoints (+ optional variation selector)
                i = 0
                while i < len(emoji_seq):
                    cp = ord(emoji_seq[i])
                    # Check if this is a surrogate pair / multi-codepoint emoji
                    emoji_char = emoji_seq[i]
                    i += 1
                    # Consume variation selectors (U+FE0F) and ZWJ sequences
                    while i < len(emoji_seq):
                        next_cp = ord(emoji_seq[i])
                        if next_cp == 0xFE0F:  # Variation selector
                            emoji_char += emoji_seq[i]
                            i += 1
                        elif next_cp == 0x200D:  # ZWJ - keep connected
                            emoji_char += emoji_seq[i]
                            i += 1
                            if i < len(emoji_seq):
                                emoji_char += emoji_seq[i]
                                i += 1
                        elif 0x1F3FB <= next_cp <= 0x1F3FF:  # Skin tone modifier
                            emoji_char += emoji_seq[i]
                            i += 1
                        else:
                            break
                    # Only count actual emojis, not standalone modifiers
                    stripped = emoji_char.strip('\ufe0f\u200d')
                    if stripped and len(stripped) >= 1:
                        emoji_counter[emoji_char] += 1

    top_emojis = emoji_counter.most_common(10)
    if top_emojis:
        print("🏆 Top 10 Emojis (sent by you):")
        for i, (emoji, count) in enumerate(top_emojis, 1):
            print(f"  {i}. {emoji} - {count:,} times")
    else:
        print("  No emojis found")

    # Prepare statistics for JSON output
    stats = {
        "year": year,
        "total_messages": total_messages,
        "sent": sent,
        "received": received,
        "total_conversations": total_chats,
        "days_in_period": days_in_period,
        "messages_per_day": messages_per_day,
        "date_range": {
            "start": str(min_dt.date()) if min_dt else None,
            "end": str(max_dt.date()) if max_dt else None
        },
        "top_individual_chats": [{"name": name, "count": count} for name, count in top_individual_chats],
        "top_groups": [{"name": name, "count": count} for name, count in top_groups],
        "top_hours": [{"hour": hour, "count": count} for hour, count in top_hours],
        "days_of_week": [{"day": day, "count": count} for day, count in days],
        "busiest_day": {"date": busiest_day_date, "count": busiest_day_count},
        "top_emojis": [{"emoji": emoji, "count": count} for emoji, count in top_emojis]
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
        messages_per_day=stats.get('messages_per_day', 0),
        days_in_period=stats.get('days_in_period', 365),
        top_individual_chats=top_individual_chats[:3],  # Top 3 for hero slides
        top_individual_chats_full=stats.get('top_individual_chats', []),  # Full top 10 for table
        top_groups=top_groups[:3],  # Top 3 for hero slides
        top_groups_full=stats.get('top_groups', []),  # Full top 10 for table
        total_conversations=stats['total_conversations'],
        date_range=stats.get('date_range', {}),
        personality=stats.get('personality', 'Chatter'),
        personality_description=stats.get('description', ''),
        busiest_day=stats.get('busiest_day', {}),
        top_emojis=stats.get('top_emojis', []),
        data_json=json.dumps(stats)
    )

    # Write HTML file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

def main():
    parser = argparse.ArgumentParser(
        description='WhatsApp Wrapped MVP - Analyze your WhatsApp conversations',
        epilog='Examples:\n'
               '  python whatsapp_wrapped_mvp.py --list-backups\n'
               '  python whatsapp_wrapped_mvp.py --year 2025\n'
               '  python whatsapp_wrapped_mvp.py --db /path/to/ChatStorage.sqlite',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--db', type=str, help='Path to ChatStorage.sqlite file (if already extracted)')
    parser.add_argument('--output', type=str, default='whatsapp_wrapped_stats.json', help='Output JSON file')
    parser.add_argument('--year', type=int, default=2025, help='Year to analyze (default: 2025, use 0 for all years)')
    parser.add_argument('--list-backups', action='store_true', help='List all discovered iOS backups')
    args = parser.parse_args()

    print("🎉 WhatsApp Wrapped MVP")
    print(f"Platform: {platform.system()} {platform.release()}\n")
    print("=" * 50)

    # Handle --list-backups flag
    if args.list_backups:
        list_backups()
        return

    # If user provided database path directly
    if args.db:
        db_path = Path(args.db)
        if not db_path.exists():
            print(f"❌ Database file not found: {db_path}")
            return
        print(f"✓ Using provided database: {db_path}")
        try:
            print(f"✓ Size: {db_path.stat().st_size / 1024 / 1024:.1f} MB")
        except Exception:
            pass
    else:
        # Find iOS backups
        print("\n[1/3] Finding iOS backups...")
        backups = find_ios_backups(verbose=False)

        if not backups:
            print("\n❌ No iOS backups found.")
            system = platform.system().lower()
            print(f"\nExpected location on {system.title()}:")
            for loc in get_backup_locations():
                print(f"  {loc.expanduser()}")
            print(get_platform_fix_instructions())
            print("\n💡 You can also manually provide the database:")
            print(f"   python {sys.argv[0]} --db /path/to/ChatStorage.sqlite")
            print(f"\n💡 Or use --list-backups to see all available backups:")
            print(f"   python {sys.argv[0]} --list-backups")
            return

        print(f"✓ Found {len(backups)} backup(s)")

        # Use the most recent backup
        backup = backups[0]
        backup_path = backup['path']
        print(f"✓ Using backup: {backup['device_name']} ({backup['id'][:8]}...)")
        if backup['backup_date']:
            date_str = backup['backup_date'].strftime('%Y-%m-%d %H:%M')
            print(f"  Date: {date_str}")

        # Find WhatsApp database
        print("\n[2/3] Looking for WhatsApp database...")
        db_path, description = find_whatsapp_db(backup_path)

        if not db_path:
            print("\n❌ WhatsApp database not found in backup.")
            print("💡 Possible reasons:")
            print("   - WhatsApp is not installed on the device")
            print("   - No messages have been sent/received yet")
            print("   - This is an incomplete backup")
            print(f"\n💡 Or provide the database manually:")
            print(f"   python {sys.argv[0]} --db /path/to/ChatStorage.sqlite")
            print(f"\n💡 To extract manually, use tools like:")
            print("   - iMazing (cross-platform)")
            print("   - 3uTools (Windows)")
            print("   - iPhone Backup Extractor")
            return

        try:
            size_mb = db_path.stat().st_size / 1024 / 1024
            print(f"✓ Found ChatStorage.sqlite ({size_mb:.1f} MB)")
            if description:
                print(f"  Method: {description}")
        except Exception as e:
            print(f"✓ Found ChatStorage.sqlite (error reading size: {e})")

    # Analyze database
    print("\n[3/3] Analyzing your WhatsApp data...")
    print("=" * 50)

    try:
        stats = analyze_whatsapp_db(db_path, year=args.year)
    except sqlite3.DatabaseError as e:
        print(f"\n❌ Database error: {e}")
        print("\n💡 The file may be corrupted or not a valid WhatsApp database.")
        print("💡 Make sure you're using ChatStorage.sqlite from an iOS backup.")
        return
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
