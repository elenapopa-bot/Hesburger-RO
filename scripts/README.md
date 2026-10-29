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
   ~/.hesburger_ro_env   # or: source ~/.hesburger_ro_env
   python3 ~/scripts/hesburger_ro_update.py
   ```

   Log: `~/scripts/hesburger_ro.log`

## Cron (Europe/Bucharest)

```cron
0 13 * * 1  source $HOME/.hesburger_ro_env && /usr/bin/python3 $HOME/scripts/hesburger_ro_update.py
0 13 2 * * source $HOME/.hesburger_ro_env && /usr/bin/python3 $HOME/scripts/hesburger_ro_update.py
```

- **Monday 13:00** — last closed week (Mon–Sun).
- **2nd of month 13:00** — roll completed month; Oct TD tab when the calendar month is still open.

The Mac must be awake, unlocked, and Chrome logged into Looker.

## Live report

https://elenapopa-bot.github.io/Hesburger-RO/
