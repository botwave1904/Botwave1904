# BOTWAVE VIP EXPERIENCE — RUNBOOK
## The exact steps to follow when running the overhaul on someone's machine

---

## THE NIGHT BEFORE (30 min prep)

### 1. Practice on your own machine first
```bash
# On YOUR Windows machine (or a test machine), run the dry run:
powershell -ExecutionPolicy Bypass -File botwave-overhaul.ps1 -DryRun
```
Read the output. Make sure you understand what it does. Look at the
HTML report it generates. Open it in a browser. This is what the
IT guy will see — make sure it looks professional.

### 2. Fill out HIS client profile
Open `config/client-profile-template.json` and fill in what you know:
- His name and company
- Industry (IT services? MSP?)
- Set `preview_only: true` (safe mode — shows what it WOULD do)
- Under `bloatware.apps_to_keep`: add anything you think he uses
  (Spotify, Discord, Teams, etc.)

### 3. Make sure YOUR garage machine is running
```bash
# SSH into your garage machine
ssh gringo@your-tailscale-ip

# Check Ollama is up
curl http://localhost:11434/api/tags

# Start Botwave
cd /path/to/botwave
./botwave-start.sh --status
```

### 4. Prep Tailscale
- Make sure Tailscale is installed on YOUR machine
- You'll need him to install Tailscale on HIS machine during the call
- Download link ready: https://tailscale.com/download

---

## THE CALL (60-90 minutes)

### Phase 1: Setup (10 min)

**What you say:**
> "Before we start, I'm going to walk you through exactly what we're
> going to do. First, I'll connect to your machine securely through
> Tailscale — it's an encrypted mesh network, no ports open to the
> internet. Then I'll run a scan of your system to see what we're
> working with. Nothing gets changed until you approve it."

**What you do:**
1. Have him download and install Tailscale: https://tailscale.com/download
2. Have him share his Tailscale IP with you
3. He needs to enable SSH access in Tailscale settings
4. Verify you can connect:
```bash
tailscale ping his-machine-name
tailscale ssh his-username@his-machine-name
```

**If Tailscale SSH doesn't work:**
- Use AnyDesk or TeamViewer as backup
- The script runs the same either way

### Phase 2: The Scan (5 min)

**What you say:**
> "OK I'm connected. First thing I'm going to do is run a dry run —
> this scans everything but doesn't change a single file. We'll look
> at the results together before I touch anything."

**What you do:**
```powershell
# Copy the script to his machine
# Then run the dry run:
powershell -ExecutionPolicy Bypass -File botwave-overhaul.ps1 -DryRun
```

**While it runs, narrate what's happening:**
> "Right now it's scanning your Desktop, Documents, and Downloads
> for business files... it found 47 invoices, 12 contracts, 23
> spreadsheets scattered across 6 different folders..."
>
> "It's checking your temp files... you've got 3.2 GB of browser
> cache and temp files we can clean up..."
>
> "Running a quick security check... Windows Defender is up to date,
> no threats detected, that's good."

### Phase 3: The Report (5 min)

**What you say:**
> "Here's the report. Let me share my screen so you can see this."

Open the HTML report in a browser. Walk through it:
- "Here's your disk space — you had X free, after cleanup you'll have Y"
- "Here are the 47 business files we found scattered around"
- "Here are the 10 largest files on your system"
- "Security scan is clean — no threats"
- "Here are the startup programs slowing down your boot"

**This is the wow moment.** Most people have never seen a professional
audit of their own machine. Let him absorb it.

### Phase 4: The Ask (2 min)

**What you say:**
> "So here's what I'd like to do with your permission. I'll organize
> all those business files into clean folders — invoices together,
> contracts together, tax docs together. Everything gets backed up
> first, so nothing is lost. I'll clean up the temp files and browser
> cache — heads up, that will log you out of any saved website logins,
> so you'll need to re-enter passwords for Chrome or Edge. I'll remove
> the bloatware like Bing News and Solitaire — do you use any of those?
> And I'll optimize your startup so it boots faster. Sound good?"

**Wait for his yes.** Don't rush this. He needs to feel in control.

**Quick questions to ask:**
- "Do you use hibernation or sleep mode?" (if yes, skip hibernate disable)
- "Do you have any antivirus besides Windows Defender?" (if Norton/McAfee, skip that section)
- "Any apps in this bloatware list you actually use?" (show him the list)
- "Anything in the Recycle Bin you need?"

### Phase 5: The Overhaul (15-20 min)

**What you do:**
```powershell
# THE REAL RUN — with his permission
powershell -ExecutionPolicy Bypass -File botwave-overhaul.ps1 -Confirm
```

**While it runs, keep talking:**
> "Phase 1 — organizing your files. It's creating a Business folder
> with subfolders for invoices, contracts, tax documents, clients...
> every file gets backed up first before it's copied anywhere."
>
> "Phase 2 — cleanup. Clearing temp files, browser caches, old
> Windows update files... there's 3 gigs we're getting back."
>
> "Phase 3 — security scan. Running Windows Defender, checking for
> any adware or potentially unwanted programs..."
>
> "Phase 4 — performance analysis. Finding the biggest files,
> cataloging all your installed apps, checking what's slowing
> down your startup..."

### Phase 6: The Reveal (5 min)

When it finishes and shows:
```
✅ Botwave Overhaul Complete — Machine is now primed and ready
   for bot deployment.
```

**Open the final HTML report.** Share screen again.

**What you say:**
> "Here's your before and after. You went from X GB free to Y GB free —
> we recovered Z GB of wasted space. Your 47 scattered business files
> are now organized in C:\Business with subfolders for each category.
> Here's your file index — every file we found, where it was, where
> it is now. Security is clean. And your machine should boot noticeably
> faster with those startup items disabled."

**Then open C:\Business in File Explorer on his screen.** Let him see
the clean folder structure. Invoices-Receipts, Contracts-Legal,
Tax-Accounting — all organized.

**Then open C:\Business\Business-File-Index.csv in Excel.** Show him
the master index of every business file on his machine.

**This is the moment.** His jaw should be on the floor.

### Phase 7: The Botwave Pitch (10 min)

**What you say:**
> "So that's what we do for every client we onboard. But the real
> product is what comes next. Let me show you what the AI does."

If you have the Telegram bot running on your garage machine:
1. Open Telegram on your phone
2. Message the bot: "my kitchen sink is clogged and won't drain"
3. Show him the instant quote that comes back
4. Say: "That just happened at 10pm on a Saturday. No employee needed."

If you have the vision model loaded:
1. Take a photo of a sink or pipe (anything plumbing-related)
2. Send it to the bot with caption "what do I need for this job?"
3. Show him the structured takeoff with materials and costs

**What you say:**
> "Every plumber you know is losing $86K a year in missed calls.
> Their phone goes to voicemail while they're on a job. 85% of those
> callers never call back — they call the next plumber on Google.
>
> Botwave answers those calls 24/7. It speaks plumber — it knows
> the difference between a drain cleaning and a slab leak. It quotes
> the right price using the contractor's actual rates. And it books
> the appointment.
>
> You know IT guys, and you know contractors. Every contractor you
> refer to us is recurring revenue for you — 20% of their monthly
> subscription. Ten clients on the Professional plan is $1,200 a month
> in passive income for you.
>
> Want me to set up a demo for one of your clients?"

### Phase 8: Close (5 min)

Leave him with:
1. The HTML report (already saved on his machine)
2. The organized Business folder (already there)
3. The partner one-pager PDF (email it)
4. The pitch deck (email it)
5. Your phone number

**Don't push for a commitment today.** He needs to process what
he just saw. The overhaul itself is the selling — he just experienced
the product. Say:

> "Take a look at the report, check out the organized files.
> If you've got a client who could use this, let me know and
> I'll do the same thing for them — first one's on me."

---

## AFTER THE CALL (15 min)

1. Send the follow-up email:
   - "Great meeting you today. Attached is your overhaul report
     and the partner info we discussed."
   - Attach: Partner one-pager PDF, pitch deck
   - Do NOT attach the overhaul report — it's already on his machine

2. Update your CRM/notes:
   - What apps did he have installed?
   - What was his reaction to the organized files?
   - Did he mention any specific clients?
   - Any objections or concerns?

3. Set a reminder to follow up in 3 days:
   - "Hey [name], did you get a chance to look through those
     organized files? Any contractors come to mind who could
     use the AI assistant?"

---

## IF SOMETHING GOES WRONG

**Script crashes mid-run:**
- Don't panic. All original files are backed up in C:\Botwave\Backups\
- The HTML report still generates even on errors
- Say: "Let me check what happened — your files are safe, everything
  is backed up." Check the log at C:\Botwave\Logs\

**Tailscale won't connect:**
- Fall back to AnyDesk or TeamViewer
- Have him download AnyDesk: https://anydesk.com

**His antivirus blocks the script:**
- This happens with Norton and McAfee
- Have him temporarily disable it, or add an exception for PowerShell
- Say: "Your antivirus is doing its job — it sees PowerShell running
  and wants to make sure it's safe. Let's add a temporary exception."

**He says "this is too expensive":**
- Don't argue about price
- Say: "What if we started with a free 30-day trial? If the bot
  captures even one extra job for your client in that month,
  it's already paid for itself."

**He says "I need to think about it":**
- Perfect. That's normal.
- Leave the report and the one-pager
- Follow up in 3 days
- The organized files on his machine are doing the selling for you
  every time he opens that Business folder
