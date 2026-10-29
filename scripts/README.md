# Hesburger RO report updater

Pulls metrics from Looker (Chrome session cookies) and publishes `index.html` to [elenapopa-bot/Hesburger-RO](https://github.com/elenapopa-bot/Hesburger-RO) via GitHub API.

## Mac setup (same as before)

1. **Python 3.11+** with dependencies:

   ```bash
   pip3 install -r scripts/requirements.txt
   ```

2. **Secrets** in `~/.hesburger_ro_env`:

   ```bash
   export GITHUB_TOKEN="ghp_..."
   ```

3. **Layout template** (CSS + static sections: dishes, refunds):

   ```bash
   mkdir -p ~/scripts
   cp scripts/hesburger_ro_template.html ~/scripts/hesburger_ro_template.html
   cp scripts/hesburger_ro_update.py ~/scripts/hesburger_ro_update.py
   chmod +x ~/scripts/hesburger_ro_update.py
   ```

   The script prefers `~/scripts/hesburger_ro_template.html`; if missing, it uses the copy next to the script in this repo.

4. **Looker**: log in to [bolt.cloud.looker.com](https://bolt.cloud.looker.com) in Chrome on the Mac that runs the job.

5. **Run manually**:

   ```bash
   python3 ~/scripts/hesburger_ro_update.py
   ```

   (The script reads `~/.hesburger_ro_env` by itself — you do not need `source`.)

   Log: `~/scripts/hesburger_ro.log`

## Cron (Europe/Bucharest)

```cron
0 13 * * 1  source $HOME/.hesburger_ro_env && /usr/bin/python3 $HOME/scripts/hesburger_ro_update.py
0 13 2 * * source $HOME/.hesburger_ro_env && /usr/bin/python3 $HOME/scripts/hesburger_ro_update.py
```

- **Monday 13:00** — last closed week (Mon–Sun).
- **2nd of month 13:00** — roll completed month; Oct TD tab when the calendar month is still open.

The Mac must be awake, unlocked, and Chrome logged into Looker.

## Easiest run on Mac (no Cursor)

1. In Finder, open the repo folder → `scripts` → double-click **`run_update.command`**.
2. If macOS blocks it: right-click → **Open** → **Open** again.
3. Log in to Looker in Chrome when asked, then press **Enter** in the Terminal window.

## Live report

https://elenapopa-bot.github.io/Hesburger-RO/
