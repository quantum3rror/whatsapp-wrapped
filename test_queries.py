import sqlite3
from pathlib import Path
base = Path.home() / 'Apple' / 'MobileSync' / 'Backup'
for d in base.iterdir():
    db = d / '7c' / '7c7fba66680ef796b916b067077cc246adacf01d'
    if db.exists():
        conn = sqlite3.connect(str(db))
        c = conn.cursor()
        df = 'AND ZMESSAGEDATE >= 757382400 AND ZMESSAGEDATE <= 788918399'

        # 1. Chat timeline for top 1 person
        c.execute(f'''
            SELECT cs.ZPARTNERNAME FROM ZWAMESSAGE m
            JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
            WHERE cs.ZPARTNERNAME IS NOT NULL AND m.ZMESSAGEDATE IS NOT NULL AND cs.ZSESSIONTYPE = 0 {df}
            GROUP BY cs.ZPARTNERNAME ORDER BY COUNT(*) DESC LIMIT 1
        ''')
        top_person = c.fetchone()[0]
        print(f'Top person: {top_person}')

        c.execute(f'''
            SELECT
                CAST(strftime('%m', datetime(m.ZMESSAGEDATE + 978307200, 'unixepoch')) AS INTEGER) as month,
                COUNT(*) as cnt
            FROM ZWAMESSAGE m
            JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
            WHERE cs.ZPARTNERNAME = ? AND m.ZMESSAGEDATE IS NOT NULL {df}
            GROUP BY month ORDER BY month
        ''', (top_person,))
        for row in c.fetchall():
            print(f'  Month {row[0]}: {row[1]}')

        # Top group
        c.execute(f'''
            SELECT cs.ZPARTNERNAME FROM ZWAMESSAGE m
            JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
            WHERE cs.ZPARTNERNAME IS NOT NULL AND m.ZMESSAGEDATE IS NOT NULL AND cs.ZSESSIONTYPE = 1 {df}
            GROUP BY cs.ZPARTNERNAME ORDER BY COUNT(*) DESC LIMIT 1
        ''')
        top_group = c.fetchone()[0]
        print(f'\nTop group: {top_group}')

        c.execute(f'''
            SELECT
                CAST(strftime('%m', datetime(m.ZMESSAGEDATE + 978307200, 'unixepoch')) AS INTEGER) as month,
                COUNT(*) as cnt
            FROM ZWAMESSAGE m
            JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
            WHERE cs.ZPARTNERNAME = ? AND m.ZMESSAGEDATE IS NOT NULL {df}
            GROUP BY month ORDER BY month
        ''', (top_group,))
        for row in c.fetchall():
            print(f'  Month {row[0]}: {row[1]}')

        # 2. Response time comparison for top 3 chats
        print(f'\n--- Response time comparison ---')
        c.execute(f'''
            SELECT cs.ZPARTNERNAME, cs.Z_PK FROM ZWAMESSAGE m
            JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
            WHERE cs.ZPARTNERNAME IS NOT NULL AND m.ZMESSAGEDATE IS NOT NULL AND cs.ZSESSIONTYPE = 0 {df}
            GROUP BY cs.ZPARTNERNAME ORDER BY COUNT(*) DESC LIMIT 3
        ''')
        top3 = c.fetchall()
        for name, zpk in top3:
            c.execute(f'''
            WITH ordered_msgs AS (
                SELECT m.ZMESSAGEDATE, m.ZISFROMME,
                    LAG(m.ZMESSAGEDATE) OVER (ORDER BY m.ZMESSAGEDATE) as prev_date,
                    LAG(m.ZISFROMME) OVER (ORDER BY m.ZMESSAGEDATE) as prev_from_me
                FROM ZWAMESSAGE m
                WHERE m.ZCHATSESSION = ? AND m.ZMESSAGEDATE IS NOT NULL {df}
            )
            SELECT
                ZISFROMME as who_replied,
                CAST(AVG(ZMESSAGEDATE - prev_date) AS INTEGER) as avg_rt,
                COUNT(*) as cnt
            FROM ordered_msgs
            WHERE prev_from_me IS NOT NULL AND ZISFROMME != prev_from_me
              AND (ZMESSAGEDATE - prev_date) > 0 AND (ZMESSAGEDATE - prev_date) < 86400
            GROUP BY ZISFROMME
            ''', (zpk,))
            rows = c.fetchall()
            you_rt = next((r for r in rows if r[0] == 1), None)
            them_rt = next((r for r in rows if r[0] == 0), None)
            print(f'{name}:')
            if you_rt: print(f'  You: avg {you_rt[1]}s = {you_rt[1]//60}m ({you_rt[2]} replies)')
            if them_rt: print(f'  Them: avg {them_rt[1]}s = {them_rt[1]//60}m ({them_rt[2]} replies)')

        # Use median instead of avg
        print(f'\n--- Response time comparison (MEDIAN) ---')
        import statistics
        for name, zpk in top3:
            c.execute(f'''
            WITH ordered_msgs AS (
                SELECT m.ZMESSAGEDATE, m.ZISFROMME,
                    LAG(m.ZMESSAGEDATE) OVER (ORDER BY m.ZMESSAGEDATE) as prev_date,
                    LAG(m.ZISFROMME) OVER (ORDER BY m.ZMESSAGEDATE) as prev_from_me
                FROM ZWAMESSAGE m
                WHERE m.ZCHATSESSION = ? AND m.ZMESSAGEDATE IS NOT NULL {df}
            )
            SELECT
                ZISFROMME,
                (ZMESSAGEDATE - prev_date) as rt
            FROM ordered_msgs
            WHERE prev_from_me IS NOT NULL AND ZISFROMME != prev_from_me
              AND (ZMESSAGEDATE - prev_date) > 0 AND (ZMESSAGEDATE - prev_date) < 86400
            ORDER BY ZISFROMME, rt
            ''', (zpk,))
            rows = c.fetchall()
            you_times = [r[1] for r in rows if r[0] == 1]
            them_times = [r[1] for r in rows if r[0] == 0]
            print(f'{name}:')
            if you_times:
                med = statistics.median(you_times)
                print(f'  You: median {med:.0f}s = {med//60:.0f}m {med%60:.0f}s ({len(you_times)} replies)')
            if them_times:
                med = statistics.median(them_times)
                print(f'  Them: median {med:.0f}s = {med//60:.0f}m {med%60:.0f}s ({len(them_times)} replies)')

        # 3. First and last message
        print(f'\n--- First & Last message ---')
        c.execute(f'''
            SELECT m.ZTEXT, cs.ZPARTNERNAME, m.ZISFROMME,
                   datetime(m.ZMESSAGEDATE + 978307200, 'unixepoch') as dt
            FROM ZWAMESSAGE m
            JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
            WHERE m.ZTEXT IS NOT NULL AND m.ZMESSAGEDATE IS NOT NULL AND cs.ZPARTNERNAME IS NOT NULL {df}
            ORDER BY m.ZMESSAGEDATE ASC LIMIT 1
        ''')
        first = c.fetchone()
        print(f'First: "{first[0][:60]}" - {first[1]} - from_me={first[2]} - {first[3]}')

        c.execute(f'''
            SELECT m.ZTEXT, cs.ZPARTNERNAME, m.ZISFROMME,
                   datetime(m.ZMESSAGEDATE + 978307200, 'unixepoch') as dt
            FROM ZWAMESSAGE m
            JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
            WHERE m.ZTEXT IS NOT NULL AND m.ZMESSAGEDATE IS NOT NULL AND cs.ZPARTNERNAME IS NOT NULL {df}
            ORDER BY m.ZMESSAGEDATE DESC LIMIT 1
        ''')
        last = c.fetchone()
        print(f'Last: "{last[0][:60]}" - {last[1]} - from_me={last[2]} - {last[3]}')

        # 4. Longest gap
        print(f'\n--- Longest gap ---')
        c.execute(f'''
            WITH msg_gaps AS (
                SELECT cs.ZPARTNERNAME,
                    m.ZMESSAGEDATE,
                    LAG(m.ZMESSAGEDATE) OVER (PARTITION BY m.ZCHATSESSION ORDER BY m.ZMESSAGEDATE) as prev_date
                FROM ZWAMESSAGE m
                JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
                WHERE m.ZMESSAGEDATE IS NOT NULL AND cs.ZPARTNERNAME IS NOT NULL AND cs.ZSESSIONTYPE = 0 {df}
            )
            SELECT ZPARTNERNAME, MAX(ZMESSAGEDATE - prev_date) as gap_seconds,
                   ROUND(MAX(ZMESSAGEDATE - prev_date) / 86400.0, 1) as gap_days
            FROM msg_gaps
            WHERE prev_date IS NOT NULL
            GROUP BY ZPARTNERNAME
            ORDER BY gap_seconds DESC
            LIMIT 1
        ''')
        row = c.fetchone()
        print(f'  {row[0]}: {row[2]} days')

        conn.close()
        break
