# WhatsApp Wrapped MVP

Generate Spotify Wrapped-style statistics for your WhatsApp conversations!

## Quick Start (MVP)

### Prerequisites

1. **macOS** with iTunes/Finder backup of your iPhone
2. **Python 3.9+**
3. **WhatsApp** installed on your iPhone with message history

### Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

### Usage

**Option 1: Automatic (requires Full Disk Access)**

```bash
# Run the MVP script - auto-finds iOS backup
python whatsapp_wrapped_mvp.py
```

**Option 2: Manual database path (recommended for now)**

```bash
# Analyze 2025 only (default)
python whatsapp_wrapped_mvp.py --db /path/to/ChatStorage.sqlite

# Analyze a different year
python whatsapp_wrapped_mvp.py --db /path/to/ChatStorage.sqlite --year 2024

# Analyze all years
python whatsapp_wrapped_mvp.py --db /path/to/ChatStorage.sqlite --year 0

# Custom output file
python whatsapp_wrapped_mvp.py --db /path/to/ChatStorage.sqlite --output my_stats.json
```

The script will:
1. 🔍 Find your iOS backups automatically (or use provided path)
2. 📱 Extract WhatsApp database from the most recent backup
3. 📊 Analyze your messages and generate statistics
4. 💾 Save results to JSON and HTML files
5. 🎉 **Open the HTML file in your browser** to see your Wrapped!

### What You'll Get

**Two output files:**

1. **JSON file** (`whatsapp_wrapped_stats.json`) - Raw statistics data
2. **HTML file** (`whatsapp_wrapped_stats.html`) - Beautiful interactive visualization!

**Statistics included:**
- **Total messages** sent and received
- **Top 3 individual chats** - Your most active 1-on-1 conversations
- **Top 3 group chats** - Your most active group conversations
- **Peak messaging hours** - when you chat the most
- **Day of week patterns** - your most active days
- **Personality classification** - Are you a Night Owl? Early Bird? Conversationalist?
- **Interactive charts** powered by Chart.js

**Controls for HTML visualization:**
- **Keyboard**: Arrow keys (← →) or Spacebar
- **Touch**: Swipe left/right on mobile
- **Mouse**: Click prev/next buttons

### Requirements for iOS Backup

#### Create an iOS Backup:

1. Connect iPhone to Mac
2. Open **Finder** (macOS Catalina+) or **iTunes** (older macOS)
3. Select your iPhone
4. Click **"Back Up Now"**
5. **Important**: For this MVP, use an **unencrypted backup**
   - Uncheck "Encrypt local backup" if prompted
   - (Encrypted backup support coming in full version)

#### Where Backups are Stored:

```
~/Library/Application Support/MobileSync/Backup/
```

### Privacy & Security

- ✅ **100% local processing** - no data sent anywhere
- ✅ **No cloud uploads** - everything stays on your computer
- ✅ **Read-only access** - your backup is never modified
- ✅ **Open source** - inspect the code yourself

## Roadmap

- [x] MVP: Basic iOS analysis with core metrics
- [ ] HTML visualization (Wrapped-style slides)
- [ ] Encrypted iOS backup support
- [ ] Android support (msgstore.db)
- [ ] Media analytics (photos, videos, voice notes)
- [ ] Emoji and sentiment analysis
- [ ] Flutter mobile app

## Troubleshooting

**"No iOS backups found"**
- Make sure you've created a backup using Finder/iTunes
- Check that backups exist at `~/Library/Application Support/MobileSync/Backup/`

**"WhatsApp database not found"**
- Ensure WhatsApp is installed on your iPhone
- Make sure you have WhatsApp message history
- Try creating a fresh backup

**"Permission denied"**
- Make sure the script has read access to your backup folder
- On macOS, you may need to grant Terminal "Full Disk Access" in System Preferences > Privacy & Security
- **Alternative**: Extract the database manually and use `--db` flag (see below)

### Manual Database Extraction (No Full Disk Access Required)

If you can't or don't want to grant Full Disk Access, you can manually extract the database:

#### Method 1: Using iMazing (Free)

1. Download [iMazing](https://imazing.com/) (free for this use case)
2. Connect your iPhone
3. Select your device → Apps → WhatsApp
4. Click "Extract App Data"
5. Find `ChatStorage.sqlite` in the extracted files
6. Run: `python whatsapp_wrapped_mvp.py --db /path/to/ChatStorage.sqlite`

#### Method 2: From Backup (Manual)

The WhatsApp database is located in your iOS backup at a specific hash. If you can access your backup folder:

```bash
# The file hash for ChatStorage.sqlite
# Located at: ~/Library/Application Support/MobileSync/Backup/{BACKUP_ID}/7c/7c7fba66680ef796b916b067077cc246adacf01d

# Copy it somewhere accessible and run:
python whatsapp_wrapped_mvp.py --db ~/Desktop/ChatStorage.sqlite
```

## Technical Details

### iOS Database Structure

WhatsApp on iOS uses a SQLite database called `ChatStorage.sqlite` stored in the app's shared container. The MVP analyzes:

- **ZWAMESSAGE** table - all messages
- **ZWACHATSESSION** table - conversations and contacts
- Apple Core Data timestamps (seconds since 2001-01-01)

### Dependencies

- Standard library only for MVP! (sqlite3, pathlib, json, etc.)
- Full version will use: pandas, jinja2, rich, etc.

## License

MIT License - feel free to use and modify!

## Contributing

This is an early MVP. Contributions welcome!

---

**Generated with ❤️ for WhatsApp users who want insights into their conversations**
