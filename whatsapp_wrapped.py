#!/usr/bin/env python3
"""
WhatsApp Wrapped - Analyze WhatsApp conversations from iOS backups

Supported Platforms:
    - macOS (Darwin): ~/Library/Application Support/MobileSync/Backup
    - Windows: ~/Apple/MobileSync/Backup (Apple Devices app, formerly iTunes)

Permission Requirements (macOS):
    Terminal needs Full Disk Access to read iOS backups:
    1. System Settings → Privacy & Security → Full Disk Access
    2. Add your terminal app (Terminal, iTerm2, etc.)
    3. Restart terminal and try again

Usage Examples:
    python whatsapp_wrapped.py --list-backups              # List all backups
    python whatsapp_wrapped.py --year 2025                 # Analyze 2025 (quiet mode)
    python whatsapp_wrapped.py --year 2023-2025            # Analyze 2023 to 2025
    python whatsapp_wrapped.py --year 0                    # Analyze all-time (quiet mode)
    python whatsapp_wrapped.py --verbose                   # Show detailed progress
    python whatsapp_wrapped.py --db /path/to/ChatStorage.sqlite  # Use specific DB
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
}

# Platform detection for Windows-specific timestamp handling
_IS_WINDOWS = platform.system() == 'Windows'

# Verbose mode flag (set by main())
verbose = False


def log(message, verbose_only=True):
    """Print message only if in verbose mode or if verbose_only=False"""
    global verbose
    if verbose or not verbose_only:
        print(message)

def get_backup_locations():
    """Get iOS backup locations for the current platform"""
    system = platform.system().lower()

    # Map platform.system() to our keys
    if system == 'darwin':
        return [Path.home() / "Library" / "Application Support" / "MobileSync" / "Backup"]
    elif system == 'windows':
        # Apple Devices app (formerly iTunes) uses ~/Apple/MobileSync/Backup
        return [Path.home() / "Apple" / "MobileSync" / "Backup"]
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
   python whatsapp_wrapped.py --db /path/to/ChatStorage.sqlite"""
    elif system == 'windows':
        return """
💡 To fix this on Windows:
   1. Open Apple Devices app (formerly iTunes)
   2. Verify your device has been backed up
   3. Check backup location: C:\\Users\\<YourName>\\Apple\\MobileSync\\Backup

💡 Alternative: Manually extract WhatsApp database
   Use a tool like iMazing or 3uTools
   Then run with --db flag:
   python whatsapp_wrapped.py --db C:\\path\\to\\ChatStorage.sqlite"""
    else:
        return """
💡 Use --db flag to provide ChatStorage.sqlite manually
   python whatsapp_wrapped.py --db /path/to/ChatStorage.sqlite"""

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
    """Windows: Use fromtimestamp for local time, fallback for edge cases"""
    if apple_timestamp is None:
        return None
    unix_timestamp = apple_timestamp + APPLE_TIMESTAMP_OFFSET
    try:
        return datetime.fromtimestamp(unix_timestamp)
    except (OSError, OverflowError, ValueError):
        return datetime(1970, 1, 1) + timedelta(seconds=unix_timestamp)

def _apple_timestamp_to_datetime_unix(apple_timestamp):
    """Unix (macOS): Use fromtimestamp (fully supported)"""
    if apple_timestamp is None:
        return None
    unix_timestamp = apple_timestamp + APPLE_TIMESTAMP_OFFSET
    return datetime.fromtimestamp(unix_timestamp)

def apple_timestamp_to_datetime(apple_timestamp):
    """Convert Apple Core Data timestamp to datetime (platform-aware)"""
    if _IS_WINDOWS:
        return _apple_timestamp_to_datetime_windows(apple_timestamp)
    return _apple_timestamp_to_datetime_unix(apple_timestamp)

def parse_year_arg(value):
    """Parse --year argument: single year (2025), range (2023-2025), or 0 (all-time).

    Returns (start_year, end_year) tuple. Both None means all-time.
    For a single year, start_year == end_year.
    """
    value = str(value).strip()
    if value == '0':
        return (None, None)
    if '-' in value:
        parts = value.split('-', 1)
        try:
            start = int(parts[0])
            end = int(parts[1])
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"Invalid year range '{value}'. Use YYYY or YYYY-YYYY (e.g., 2025 or 2023-2025)")
        if start > end:
            raise argparse.ArgumentTypeError(
                f"Invalid range: start year {start} is after end year {end}")
        if start < 2009:
            raise argparse.ArgumentTypeError(
                f"Invalid start year {start}. WhatsApp was released in 2009.")
        return (start, end)
    try:
        year = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid year '{value}'. Use YYYY, YYYY-YYYY, or 0 for all-time.")
    if year < 0:
        raise argparse.ArgumentTypeError(f"Year must be >= 0, got {year}")
    if year > 0 and year < 2009:
        raise argparse.ArgumentTypeError(
            f"Invalid year {year}. WhatsApp was released in 2009.")
    return (year, year)

def get_year_timestamp_bounds(year, end_year=None):
    """Get Apple timestamp bounds for a given year or year range"""
    if end_year is None:
        end_year = year

    # Start of start_year (Jan 1, 00:00:00)
    start_dt = datetime(year, 1, 1, 0, 0, 0)
    start_unix = int(start_dt.timestamp())
    start_apple = start_unix - APPLE_TIMESTAMP_OFFSET

    # End of end_year (Dec 31, 23:59:59)
    end_dt = datetime(end_year, 12, 31, 23, 59, 59)
    end_unix = int(end_dt.timestamp())
    end_apple = end_unix - APPLE_TIMESTAMP_OFFSET

    return start_apple, end_apple

def analyze_whatsapp_db(db_path, year=None, end_year=None):
    """Analyze WhatsApp database and extract statistics

    Args:
        db_path: Path to the SQLite database
        year: Start year (or single year). None/0 = all-time.
        end_year: End year for range queries. None = same as year.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Set up date filtering
    if year and year > 0:
        if end_year is None:
            end_year = year
        start_ts, end_ts = get_year_timestamp_bounds(year, end_year)
        date_filter = f"AND ZMESSAGEDATE >= {start_ts} AND ZMESSAGEDATE <= {end_ts}"
        if year == end_year:
            log(f"🗓️  Filtering for year: {year}\n", verbose_only=True)
        else:
            log(f"🗓️  Filtering for range: {year}–{end_year}\n", verbose_only=True)
    else:
        date_filter = ""
        year = None  # Ensure None for "all years"
        end_year = None

    log("📊 Analyzing WhatsApp database...\n", verbose_only=True)

    # Get total message count
    cursor.execute(f"SELECT COUNT(*) FROM ZWAMESSAGE WHERE ZMESSAGEDATE IS NOT NULL {date_filter}")
    total_messages = cursor.fetchone()[0]
    log(f"✓ Total messages: {total_messages:,}", verbose_only=True)

    # Get date range
    cursor.execute("""
        SELECT MIN(ZMESSAGEDATE), MAX(ZMESSAGEDATE)
        FROM ZWAMESSAGE
        WHERE ZMESSAGEDATE IS NOT NULL
    """)
    min_date, max_date = cursor.fetchone()
    min_dt = apple_timestamp_to_datetime(min_date)
    max_dt = apple_timestamp_to_datetime(max_date)
    log(f"✓ Date range: {min_dt.date() if min_dt else 'N/A'} to {max_dt.date() if max_dt else 'N/A'}", verbose_only=True)

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
    log(f"✓ Sent: {sent:,} | Received: {received:,}", verbose_only=True)

    # Total conversations
    cursor.execute(f"SELECT COUNT(DISTINCT ZCHATSESSION) FROM ZWAMESSAGE WHERE ZMESSAGEDATE IS NOT NULL {date_filter}")
    total_chats = cursor.fetchone()[0]
    log(f"✓ Total conversations: {total_chats}", verbose_only=True)

    # Top individual chats (ZSESSIONTYPE = 0 for private/individual)
    cursor.execute(f"""
        SELECT
            cs.ZPARTNERNAME,
            COUNT(*) as msg_count,
            SUM(CASE WHEN m.ZISFROMME = 1 THEN 1 ELSE 0 END) as sent_count
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

    log("\n🏆 Top 10 Individual Chats:", verbose_only=True)
    for i, (name, count, sent_c) in enumerate(top_individual_chats, 1):
        pct = round(sent_c / count * 100, 1) if count > 0 else 0
        log(f"  {i}. {name}: {count:,} messages ({pct}% sent)", verbose_only=True)

    # Top group chats (ZSESSIONTYPE = 1 for groups)
    cursor.execute(f"""
        SELECT
            cs.ZPARTNERNAME,
            COUNT(*) as msg_count,
            SUM(CASE WHEN m.ZISFROMME = 1 THEN 1 ELSE 0 END) as sent_count
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

    log("\n👥 Top 10 Group Chats:", verbose_only=True)
    for i, (name, count, sent_c) in enumerate(top_groups, 1):
        pct = round(sent_c / count * 100, 1) if count > 0 else 0
        log(f"  {i}. {name}: {count:,} messages ({pct}% sent)", verbose_only=True)

    # Messages by hour (all 24 hours)
    cursor.execute(f"""
        SELECT
            CAST(strftime('%H', datetime(ZMESSAGEDATE + 978307200, 'unixepoch')) AS INTEGER) as hour,
            COUNT(*) as count
        FROM ZWAMESSAGE
        WHERE ZMESSAGEDATE IS NOT NULL {date_filter}
        GROUP BY hour
        ORDER BY hour ASC
    """)
    all_hours = cursor.fetchall()

    # Also keep top 5 for backward compat
    top_hours = sorted(all_hours, key=lambda x: x[1], reverse=True)[:5]

    log("\n⏰ Top 5 Messaging Hours:", verbose_only=True)
    for hour, count in top_hours:
        log(f"  {hour:02d}:00 - {count:,} messages", verbose_only=True)

    # Messages by day of week
    cursor.execute(f"""
        SELECT
            CAST(strftime('%w', datetime(ZMESSAGEDATE + 978307200, 'unixepoch')) AS INTEGER) as day_num,
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
        GROUP BY day_num
        ORDER BY day_num ASC
    """)
    days = cursor.fetchall()

    log("\n📅 Messages by Day of Week:", verbose_only=True)
    for day_num, day, count in days:
        log(f"  {day}: {count:,} messages", verbose_only=True)

    # Calculate days in analysis period
    if year and year > 0:
        period_start = datetime(year, 1, 1)
        period_end_year = end_year if end_year else year
        period_end = min(datetime(period_end_year, 12, 31), datetime.now())
        days_in_period = max((period_end - period_start).days, 1)
    elif min_dt and max_dt:
        days_in_period = max((max_dt - min_dt).days, 1)
    else:
        days_in_period = 365

    messages_per_day = round(total_messages / days_in_period, 1)
    log(f"✓ Messages per day: {messages_per_day}", verbose_only=True)

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
        log(f"\n🔥 Busiest day: {busiest_day_date} with {busiest_day_count:,} messages", verbose_only=True)
    else:
        busiest_day_date, busiest_day_count = None, 0

    # Top emojis from sent messages
    log("\n😂 Analyzing emojis...", verbose_only=True)
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
        log("🏆 Top 10 Emojis (sent by you):", verbose_only=True)
        for i, (emoji, count) in enumerate(top_emojis, 1):
            log(f"  {i}. {emoji} - {count:,} times", verbose_only=True)
    else:
        log("  No emojis found", verbose_only=True)

    # Most frequently sent message
    cursor.execute(f"""
        SELECT ZTEXT, COUNT(*) as cnt
        FROM ZWAMESSAGE
        WHERE ZTEXT IS NOT NULL
          AND ZISFROMME = 1
          AND ZMESSAGEDATE IS NOT NULL
          AND length(ZTEXT) >= 2
          {date_filter}
        GROUP BY ZTEXT
        ORDER BY cnt DESC
        LIMIT 10
    """)
    top_messages = cursor.fetchall()
    if top_messages:
        log("\n💬 Most sent messages:", verbose_only=True)
        for i, (text, count) in enumerate(top_messages, 1):
            display = text[:50] + ('...' if len(text) > 50 else '')
            log(f"  {i}. \"{display}\" - {count:,} times", verbose_only=True)
    else:
        top_messages = []

    # Media types breakdown
    cursor.execute(f"""
        SELECT ZMESSAGETYPE, COUNT(*) as cnt
        FROM ZWAMESSAGE
        WHERE ZMESSAGEDATE IS NOT NULL {date_filter}
        GROUP BY ZMESSAGETYPE
        ORDER BY cnt DESC
    """)
    raw_media = cursor.fetchall()
    media_type_map = {
        0: 'Text', 1: 'Photos', 2: 'Videos', 3: 'Audio',
        4: 'Contact Cards', 5: 'Locations', 6: 'Calls', 7: 'Links',
        8: 'Documents', 10: 'Deleted', 11: 'Stickers',
        14: 'GIFs', 15: 'Stickers',
        38: 'View Once', 39: 'View Once',
        46: 'Polls', 59: 'Reactions',
    }
    media_counts = []
    for mtype, cnt in raw_media:
        label = media_type_map.get(mtype, None)
        if label is None:
            label = 'Other'
        # Merge duplicate labels (e.g. Stickers type 11 + 15, View Once 38 + 39)
        existing = next((m for m in media_counts if m['type'] == label), None)
        if existing:
            existing['count'] += cnt
            continue
        media_counts.append({'type': label, 'count': cnt})
    media_counts.sort(key=lambda x: x['count'], reverse=True)

    log("\n📎 Media breakdown:", verbose_only=True)
    for m in media_counts[:8]:
        log(f"  {m['type']}: {m['count']:,}", verbose_only=True)

    # Messages per month
    cursor.execute(f"""
        SELECT
            CAST(strftime('%m', datetime(ZMESSAGEDATE + 978307200, 'unixepoch')) AS INTEGER) as month,
            COUNT(*) as count
        FROM ZWAMESSAGE
        WHERE ZMESSAGEDATE IS NOT NULL {date_filter}
        GROUP BY month
        ORDER BY month ASC
    """)
    messages_per_month = cursor.fetchall()
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    log("\n📅 Messages per month:", verbose_only=True)
    for month_num, count in messages_per_month:
        name = month_names[month_num - 1] if 1 <= month_num <= 12 else str(month_num)
        log(f"  {name}: {count:,}", verbose_only=True)

    # Personal response time (individual chats only)
    log("\n⏱️  Calculating response time...", verbose_only=True)
    cursor.execute(f"""
        WITH ordered_msgs AS (
            SELECT
                m.ZCHATSESSION,
                m.ZMESSAGEDATE,
                m.ZISFROMME,
                LAG(m.ZMESSAGEDATE) OVER (PARTITION BY m.ZCHATSESSION ORDER BY m.ZMESSAGEDATE) as prev_date,
                LAG(m.ZISFROMME) OVER (PARTITION BY m.ZCHATSESSION ORDER BY m.ZMESSAGEDATE) as prev_from_me
            FROM ZWAMESSAGE m
            JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
            WHERE m.ZMESSAGEDATE IS NOT NULL
              AND cs.ZSESSIONTYPE = 0
              {date_filter}
        )
        SELECT
            (ZMESSAGEDATE - prev_date) as response_seconds
        FROM ordered_msgs
        WHERE ZISFROMME = 1 AND prev_from_me = 0
          AND (ZMESSAGEDATE - prev_date) > 0
          AND (ZMESSAGEDATE - prev_date) < 86400
        ORDER BY response_seconds
    """)
    response_times = [r[0] for r in cursor.fetchall()]

    if response_times:
        import statistics
        avg_response = round(statistics.mean(response_times))
        median_response = round(statistics.median(response_times))
        under1 = sum(1 for t in response_times if t < 60)
        under5 = sum(1 for t in response_times if t < 300)
        under1h = sum(1 for t in response_times if t < 3600)
        total_responses = len(response_times)

        response_time = {
            "median_seconds": median_response,
            "average_seconds": avg_response,
            "total_responses": total_responses,
            "under_1min_pct": round(under1 / total_responses * 100, 1),
            "under_5min_pct": round(under5 / total_responses * 100, 1),
            "under_1h_pct": round(under1h / total_responses * 100, 1),
        }
        log(f"  Median response time: {median_response}s ({median_response // 60}m {median_response % 60}s)", verbose_only=True)
        log(f"  Average response time: {avg_response}s ({avg_response // 60}m {avg_response % 60}s)", verbose_only=True)
        log(f"  Under 1 min: {response_time['under_1min_pct']}%", verbose_only=True)
        log(f"  Under 5 min: {response_time['under_5min_pct']}%", verbose_only=True)
        log(f"  Under 1 hour: {response_time['under_1h_pct']}%", verbose_only=True)
    else:
        response_time = None
        log("  No response time data available", verbose_only=True)

    # Chat timeline for top 1 person and top 1 group (messages per month)
    log("\n📈 Chat timelines...", verbose_only=True)
    chat_timelines = {}
    is_multi_year = (year and end_year and year != end_year) or not (year and year > 0)
    is_lifetime = not (year and year > 0)

    if is_multi_year:
        # Multi-year or lifetime mode: group by year+month for full history
        timeline_select = """CAST(strftime('%Y', datetime(m.ZMESSAGEDATE + 978307200, 'unixepoch')) AS INTEGER) as yr,
                CAST(strftime('%m', datetime(m.ZMESSAGEDATE + 978307200, 'unixepoch')) AS INTEGER) as month"""
        timeline_group = "GROUP BY yr, month ORDER BY yr, month"
    else:
        # Single year: group by month only
        timeline_select = """NULL as yr,
                CAST(strftime('%m', datetime(m.ZMESSAGEDATE + 978307200, 'unixepoch')) AS INTEGER) as month"""
        timeline_group = "GROUP BY month ORDER BY month"

    def build_timeline_months(rows, is_multi_year_mode):
        result = []
        for yr, m, c in rows:
            entry = {"month": m, "count": c}
            if is_multi_year_mode:
                entry["year"] = yr
                entry["label"] = f"{month_names[m-1]} {yr}"
            else:
                entry["name"] = month_names[m-1]
                entry["label"] = month_names[m-1]
            result.append(entry)
        return result

    if top_individual_chats:
        top1_name = top_individual_chats[0][0]
        cursor.execute(f"""
            SELECT {timeline_select}, COUNT(*) as cnt
            FROM ZWAMESSAGE m
            JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
            WHERE cs.ZPARTNERNAME = ? AND m.ZMESSAGEDATE IS NOT NULL {date_filter}
            {timeline_group}
        """, (top1_name,))
        months_data = build_timeline_months(cursor.fetchall(), is_multi_year)
        chat_timelines['top_chat'] = {
            'name': top1_name,
            'months': months_data,
            'is_lifetime': is_multi_year
        }
        log(f"  {top1_name}: {sum(x['count'] for x in months_data):,} msgs over {len(months_data)} months", verbose_only=True)

    if top_groups:
        top1_group = top_groups[0][0]
        cursor.execute(f"""
            SELECT {timeline_select}, COUNT(*) as cnt
            FROM ZWAMESSAGE m
            JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
            WHERE cs.ZPARTNERNAME = ? AND m.ZMESSAGEDATE IS NOT NULL {date_filter}
            {timeline_group}
        """, (top1_group,))
        months_data = build_timeline_months(cursor.fetchall(), is_multi_year)
        chat_timelines['top_group'] = {
            'name': top1_group,
            'months': months_data,
            'is_lifetime': is_multi_year
        }
        log(f"  {top1_group}: {sum(x['count'] for x in months_data):,} msgs over {len(months_data)} months", verbose_only=True)

    # Response time comparison for top 3 individual chats
    log("\n⚡ Response time comparison...", verbose_only=True)
    response_comparison = []
    if top_individual_chats:
        top3_names = [c[0] for c in top_individual_chats[:3]]
        for chat_name in top3_names:
            cursor.execute(f"""
                WITH ordered_msgs AS (
                    SELECT m.ZMESSAGEDATE, m.ZISFROMME,
                        LAG(m.ZMESSAGEDATE) OVER (ORDER BY m.ZMESSAGEDATE) as prev_date,
                        LAG(m.ZISFROMME) OVER (ORDER BY m.ZMESSAGEDATE) as prev_from_me
                    FROM ZWAMESSAGE m
                    JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
                    WHERE cs.ZPARTNERNAME = ? AND cs.ZSESSIONTYPE = 0
                      AND m.ZMESSAGEDATE IS NOT NULL {date_filter}
                )
                SELECT
                    ZISFROMME,
                    (ZMESSAGEDATE - prev_date) as rt
                FROM ordered_msgs
                WHERE prev_from_me IS NOT NULL AND ZISFROMME != prev_from_me
                  AND (ZMESSAGEDATE - prev_date) > 0 AND (ZMESSAGEDATE - prev_date) < 86400
                ORDER BY ZISFROMME, rt
            """, (chat_name,))
            rows = cursor.fetchall()
            you_times = [r[1] for r in rows if r[0] == 1]
            them_times = [r[1] for r in rows if r[0] == 0]

            if you_times and them_times:
                you_med = round(statistics.median(you_times))
                them_med = round(statistics.median(them_times))
                entry = {
                    'name': chat_name,
                    'you_median': you_med,
                    'them_median': them_med,
                    'you_replies': len(you_times),
                    'them_replies': len(them_times),
                }
                response_comparison.append(entry)
                log(f"  {chat_name}: You {you_med}s vs Them {them_med}s", verbose_only=True)
            else:
                log(f"  {chat_name}: Skipped (you_replies={len(you_times)}, them_replies={len(them_times)})", verbose_only=True)

    # First and last message of the year (with context messages)
    log("\n✉️  First & last message...", verbose_only=True)

    def fetch_message_with_context(cursor, date_filter, order, from_me_filter=None, context_count=3):
        """Fetch the first/last message and surrounding context from the same chat.
        from_me_filter: None=any, 1=sent, 0=received"""
        from_me_clause = ""
        if from_me_filter is not None:
            from_me_clause = f"AND m.ZISFROMME = {from_me_filter}"

        cursor.execute(f"""
            SELECT m.ZTEXT, cs.ZPARTNERNAME, m.ZISFROMME,
                   m.ZMESSAGEDATE, m.ZCHATSESSION
            FROM ZWAMESSAGE m
            JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
            WHERE m.ZTEXT IS NOT NULL AND m.ZMESSAGEDATE IS NOT NULL
              AND cs.ZPARTNERNAME IS NOT NULL {date_filter} {from_me_clause}
            ORDER BY m.ZMESSAGEDATE {order} LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            return None
        dt_obj = apple_timestamp_to_datetime(row[3])
        main_msg = {
            'text': row[0][:100],
            'chat': row[1],
            'from_me': row[2] == 1,
            'date': dt_obj.strftime('%Y-%m-%d'),
            'time': dt_obj.strftime('%H:%M'),
        }
        chat_session = row[4]
        msg_date = row[3]

        # Fetch context: messages just before (for first) or just after (for last)
        if order == 'ASC':
            # First message: get a few messages AFTER it in the same chat for context thread
            cursor.execute(f"""
                SELECT m.ZTEXT, m.ZISFROMME, m.ZMESSAGEDATE
                FROM ZWAMESSAGE m
                WHERE m.ZCHATSESSION = ? AND m.ZMESSAGEDATE > ?
                  AND m.ZTEXT IS NOT NULL AND m.ZMESSAGEDATE IS NOT NULL
                ORDER BY m.ZMESSAGEDATE ASC LIMIT ?
            """, (chat_session, msg_date, context_count))
        else:
            # Last message: get a few messages BEFORE it in the same chat
            cursor.execute(f"""
                SELECT m.ZTEXT, m.ZISFROMME, m.ZMESSAGEDATE
                FROM ZWAMESSAGE m
                WHERE m.ZCHATSESSION = ? AND m.ZMESSAGEDATE < ?
                  AND m.ZTEXT IS NOT NULL AND m.ZMESSAGEDATE IS NOT NULL
                ORDER BY m.ZMESSAGEDATE DESC LIMIT ?
            """, (chat_session, msg_date, context_count))

        context_rows = cursor.fetchall()
        context_msgs = []
        for cr in context_rows:
            ctx_dt = apple_timestamp_to_datetime(cr[2])
            context_msgs.append({
                'text': cr[0][:100],
                'from_me': cr[1] == 1,
                'time': ctx_dt.strftime('%H:%M'),
            })

        if order == 'DESC':
            context_msgs.reverse()  # chronological order

        main_msg['context'] = context_msgs
        return main_msg

    # Fetch first sent and first received
    first_message_sent = fetch_message_with_context(cursor, date_filter, 'ASC', from_me_filter=1)
    first_message_received = fetch_message_with_context(cursor, date_filter, 'ASC', from_me_filter=0)
    if first_message_sent:
        log(f"  First sent: \"{first_message_sent['text'][:50]}\" → {first_message_sent['chat']} - {first_message_sent['date']} {first_message_sent['time']}", verbose_only=True)
    if first_message_received:
        log(f"  First received: \"{first_message_received['text'][:50]}\" ← {first_message_received['chat']} - {first_message_received['date']} {first_message_received['time']}", verbose_only=True)

    # Fetch last sent and last received
    last_message_sent = fetch_message_with_context(cursor, date_filter, 'DESC', from_me_filter=1)
    last_message_received = fetch_message_with_context(cursor, date_filter, 'DESC', from_me_filter=0)
    if last_message_sent:
        log(f"  Last sent: \"{last_message_sent['text'][:50]}\" → {last_message_sent['chat']} - {last_message_sent['date']} {last_message_sent['time']}", verbose_only=True)
    if last_message_received:
        log(f"  Last received: \"{last_message_received['text'][:50]}\" ← {last_message_received['chat']} - {last_message_received['date']} {last_message_received['time']}", verbose_only=True)

    # Longest gap in a chat
    log("\n🕳️  Longest gap...", verbose_only=True)
    cursor.execute(f"""
        WITH msg_gaps AS (
            SELECT cs.ZPARTNERNAME,
                m.ZMESSAGEDATE,
                LAG(m.ZMESSAGEDATE) OVER (PARTITION BY m.ZCHATSESSION ORDER BY m.ZMESSAGEDATE) as prev_date
            FROM ZWAMESSAGE m
            JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
            WHERE m.ZMESSAGEDATE IS NOT NULL AND cs.ZPARTNERNAME IS NOT NULL
              AND cs.ZSESSIONTYPE = 0 {date_filter}
        )
        SELECT ZPARTNERNAME, MAX(ZMESSAGEDATE - prev_date) as gap_seconds
        FROM msg_gaps
        WHERE prev_date IS NOT NULL
        GROUP BY ZPARTNERNAME
        ORDER BY gap_seconds DESC
        LIMIT 1
    """)
    gap_row = cursor.fetchone()
    longest_gap = None
    if gap_row:
        gap_days = round(gap_row[1] / 86400, 1)
        longest_gap = {
            'chat': gap_row[0],
            'seconds': gap_row[1],
            'days': gap_days,
        }
        log(f"  {longest_gap['chat']}: {gap_days} days", verbose_only=True)

    # Prepare statistics for JSON output
    stats = {
        "year": year,
        "year_end": end_year,
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
        "top_individual_chats": [{"name": name, "count": count, "sent": sent_c, "sent_pct": round(sent_c / count * 100, 1) if count > 0 else 0} for name, count, sent_c in top_individual_chats],
        "top_groups": [{"name": name, "count": count, "sent": sent_c, "sent_pct": round(sent_c / count * 100, 1) if count > 0 else 0} for name, count, sent_c in top_groups],
        "top_hours": [{"hour": hour, "count": count} for hour, count in top_hours],
        "all_hours": [{"hour": hour, "count": count} for hour, count in all_hours],
        "days_of_week": [{"day": day, "count": count} for day_num, day, count in days],
        "busiest_day": {"date": busiest_day_date, "count": busiest_day_count},
        "top_emojis": [{"emoji": emoji, "count": count} for emoji, count in top_emojis],
        "top_messages": [{"text": text, "count": count} for text, count in top_messages],
        "media_counts": media_counts,
        "messages_per_month": [{"month": m, "name": month_names[m - 1] if 1 <= m <= 12 else str(m), "count": c} for m, c in messages_per_month],
        "response_time": response_time,
        "chat_timelines": chat_timelines,
        "response_comparison": response_comparison,
        "first_message_sent": first_message_sent,
        "first_message_received": first_message_received,
        "last_message_sent": last_message_sent,
        "last_message_received": last_message_received,
        "longest_gap": longest_gap
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
        log(f"⚠️  Template not found at {template_path}", verbose_only=False)
        log("   HTML generation skipped.", verbose_only=False)
        return

    with open(template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()

    # Prepare data for template
    year = stats.get('year')
    year_end = stats.get('year_end')
    if year and year_end and year != year_end:
        year_display = f"{year}–{year_end}"
    elif year:
        year_display = str(year)
    else:
        year_display = 'All Time'

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
        personality_traits=stats.get('traits', []),
        busiest_day=stats.get('busiest_day', {}),
        top_emojis=stats.get('top_emojis', []),
        top_messages=stats.get('top_messages', []),
        media_counts=stats.get('media_counts', []),
        messages_per_month=stats.get('messages_per_month', []),
        response_time=stats.get('response_time'),
        chat_timelines=stats.get('chat_timelines', {}),
        response_comparison=stats.get('response_comparison', []),
        first_message_sent=stats.get('first_message_sent'),
        first_message_received=stats.get('first_message_received'),
        last_message_sent=stats.get('last_message_sent'),
        last_message_received=stats.get('last_message_received'),
        longest_gap=stats.get('longest_gap'),
        data_json=json.dumps(stats)
    )

    # Write HTML file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

def main():
    parser = argparse.ArgumentParser(
        description='WhatsApp Wrapped - Analyze your WhatsApp conversations',
        epilog='Examples:\n'
               '  python whatsapp_wrapped.py --list-backups\n'
               '  python whatsapp_wrapped.py --year 2025\n'
               '  python whatsapp_wrapped.py --year 2023-2025\n'
               '  python whatsapp_wrapped.py --db /path/to/ChatStorage.sqlite',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--db', type=str, help='Path to ChatStorage.sqlite file (if already extracted)')
    parser.add_argument('--output', type=str, default='whatsapp_wrapped_stats.json', help='Output JSON file')
    parser.add_argument('--year', type=str, default='2025', help='Year or range to analyze (e.g., 2025, 2023-2025, or 0 for all years)')
    parser.add_argument('--list-backups', action='store_true', help='List all discovered iOS backups')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed progress and statistics')
    args = parser.parse_args()

    # Set global verbose flag
    global verbose
    verbose = args.verbose

    log("🎉 WhatsApp Wrapped", verbose_only=False)
    log(f"Platform: {platform.system()} {platform.release()}\n", verbose_only=True)
    log("=" * 50, verbose_only=True)

    # Handle --list-backups flag
    if args.list_backups:
        list_backups()
        return

    # Parse year argument
    try:
        start_year, end_year = parse_year_arg(args.year)
    except argparse.ArgumentTypeError as e:
        log(f"\n\u274c {e}", verbose_only=False)
        return

    # If user provided database path directly
    if args.db:
        db_path = Path(args.db)
        if not db_path.exists():
            log(f"❌ Database file not found: {db_path}", verbose_only=False)
            return
        log(f"✓ Using provided database: {db_path}", verbose_only=False)
        try:
            log(f"✓ Size: {db_path.stat().st_size / 1024 / 1024:.1f} MB", verbose_only=True)
        except Exception:
            pass
    else:
        # Find iOS backups
        log("\n[1/3] Finding iOS backups...", verbose_only=True)
        backups = find_ios_backups(verbose=False)

        if not backups:
            log("\n❌ No iOS backups found.", verbose_only=False)
            system = platform.system().lower()
            log(f"\nExpected location on {system.title()}:", verbose_only=False)
            for loc in get_backup_locations():
                log(f"  {loc.expanduser()}", verbose_only=False)
            log(get_platform_fix_instructions(), verbose_only=False)
            log("\n💡 You can also manually provide the database:", verbose_only=False)
            log(f"   python {sys.argv[0]} --db /path/to/ChatStorage.sqlite", verbose_only=False)
            log(f"\n💡 Or use --list-backups to see all available backups:", verbose_only=False)
            log(f"   python {sys.argv[0]} --list-backups", verbose_only=False)
            return

        log(f"✓ Found {len(backups)} backup(s)", verbose_only=True)

        # Use the most recent backup
        backup = backups[0]
        backup_path = backup['path']
        log(f"✓ Using backup: {backup['device_name']} ({backup['id'][:8]}...)", verbose_only=True)
        if backup['backup_date']:
            date_str = backup['backup_date'].strftime('%Y-%m-%d %H:%M')
            log(f"  Date: {date_str}", verbose_only=True)

        # Find WhatsApp database
        log("\n[2/3] Looking for WhatsApp database...", verbose_only=True)
        db_path, description = find_whatsapp_db(backup_path, verbose=verbose)

        if not db_path:
            log("\n❌ WhatsApp database not found in backup.", verbose_only=False)
            log("💡 Possible reasons:", verbose_only=False)
            log("   - WhatsApp is not installed on the device", verbose_only=False)
            log("   - No messages have been sent/received yet", verbose_only=False)
            log("   - This is an incomplete backup", verbose_only=False)
            log(f"\n💡 Or provide the database manually:", verbose_only=False)
            log(f"   python {sys.argv[0]} --db /path/to/ChatStorage.sqlite", verbose_only=False)
            log(f"\n💡 To extract manually, use tools like:", verbose_only=False)
            log("   - iMazing (cross-platform)", verbose_only=False)
            log("   - 3uTools (Windows)", verbose_only=False)
            log("   - iPhone Backup Extractor", verbose_only=False)
            return

        try:
            size_mb = db_path.stat().st_size / 1024 / 1024
            log(f"✓ Found ChatStorage.sqlite ({size_mb:.1f} MB)", verbose_only=True)
            if description:
                log(f"  Method: {description}", verbose_only=True)
        except Exception as e:
            log(f"✓ Found ChatStorage.sqlite (error reading size: {e})", verbose_only=True)

    # Analyze database
    log("\n[3/3] Analyzing your WhatsApp data...", verbose_only=False)
    log("=" * 50, verbose_only=True)

    try:
        stats = analyze_whatsapp_db(db_path, year=start_year, end_year=end_year)
    except sqlite3.DatabaseError as e:
        log(f"\n❌ Database error: {e}", verbose_only=False)
        log("\n💡 The file may be corrupted or not a valid WhatsApp database.", verbose_only=False)
        log("💡 Make sure you're using ChatStorage.sqlite from an iOS backup.", verbose_only=False)
        return
    except Exception as e:
        log(f"\n❌ Error analyzing database: {e}", verbose_only=False)
        log("\n💡 Make sure the file is a valid WhatsApp ChatStorage.sqlite database", verbose_only=False)
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
        log(f"\n⚠️  HTML generation failed: {e}", verbose_only=False)
        html_generated = False

    log("\n" + "=" * 50, verbose_only=True)
    if start_year and end_year and start_year != end_year:
        year_msg = f" for {start_year}–{end_year}"
    elif start_year and start_year > 0:
        year_msg = f" for {start_year}"
    else:
        year_msg = ""
    log(f"✅ Analysis complete{year_msg}!", verbose_only=False)
    log(f"📊 Statistics saved to: {args.output}", verbose_only=False)
    if html_generated:
        log(f"🎉 HTML visualization: {html_output}", verbose_only=False)
        log(f"\n💡 Open {html_output} in your browser to see your Wrapped!", verbose_only=False)
    log("\n🔒 Privacy: All data processed locally. Nothing sent anywhere.", verbose_only=False)

if __name__ == "__main__":
    main()
