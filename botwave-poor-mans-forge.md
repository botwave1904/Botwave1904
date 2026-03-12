# Botwave Poor Man's Forge Cheat Sheet
Free Multi-AI + OpenClaw Setup — $0 APIs, privacy-first

## Goal
Chain Grok (strategy) → Gemini (edit) → Ollama local (polish) via Critique Keeper loop — $0 ongoing costs.

---

## 1. System Audit & Cleanup

```bash
# Audit folders
ls -la ~/Desktop ~/Downloads ~/Documents

# Find api files
find ~/ -name "*api*" -o -name "*key*" -o -name "*apis.txt" 2>/dev/null

# Check processes
ps aux | grep -E 'ollama|docker|node|python|claude|openclaw'

# Disk usage
du -sh ~/* | sort -hr | head -10
```

### Cleanup (safe/reversible)
```bash
# Secure api file
mkdir -p ~/.apiconfig
mv ~/Desktop/claw.txt ~/.apiconfig/apis.txt
chmod 600 ~/.apiconfig/apis.txt

# Backup
cp -r ~/.apiconfig ~/Desktop/backup-apis-$(date +%F)
```

---

## 2. Ollama Prep (Free Local "Claude")

```bash
# Install
curl -fsSL https://ollama.com/install.sh | sh

# Run in background
ollama serve &

# Pull models (32GB+ RAM for 30B)
ollama pull qwen3-coder:30b
ollama pull deepseek-coder:33b
ollama pull glm-4.7-flash:q8_0  # Lighter/fast

# Test
ollama run qwen3-coder:30b "Hello"
```

---

## 3. OpenClaw Config

Config location: `~/.apiconfig/openclaw.json`

```json
{
  "version": "1.0",
  "name": "Botwave Poor Man's Forge",
  "primary": "ollama",
  "debug": true,
  "providers": {
    "ollama": {
      "enabled": true,
      "endpoint": "http://localhost:11434",
      "model": "qwen3-coder:30b",
      "api_key": "ollama"
    },
    "openrouter": {
      "enabled": true,
      "api_key": "sk-or-v1-...",
      "model": "deepseek/deepseek-chat"
    },
    "groq": {
      "enabled": true,
      "api_key": "gsk_...",
      "model": "llama-3.3-70b-versatile"
    },
    "xai": {
      "enabled": true,
      "api_key": "xai-...",
      "model": "grok-2"
    },
    "gemini": {
      "enabled": true,
      "api_key": "AIza...",
      "model": "gemini-2.0-flash"
    }
  },
  "telegram": {
    "enabled": true,
    "bot_token": "8747407183:AAHimCXAm0SleFh7DCW_xxmH7vn09nnAZ3k",
    "allowed_users": ["8711428786"]
  },
  "chain": {
    "strategy": "xai",
    "edit": "gemini",
    "polish": "ollama",
    "fallback": ["groq", "openrouter"]
  },
  "features": {
    "critique_keeper": true,
    "code_review": true,
    "privacy_first": true
  }
}
```

### Run OpenClaw
```bash
openclaw gateway --port 18789 --verbose
```

---

## 4. Available Keys (from claw.txt)

| Provider | Key | Model |
|----------|-----|-------|
| OpenRouter | sk-or-v1-eefb... | deepseek-chat |
| xAI (Grok) | xai-jZQPk... | grok-2 |
| Gemini | AIzaSyC76V... | gemini-2.0-flash |
| Groq | gsk_ePWQf... | llama-3.3-70b |
| Brave | BSAVYmWe... | (disabled) |

### Telegram Bots (8 total)
- Boti1904: `8747407183:AAHimCXAm0SleFh7DCW_xxmH7vn09nnAZ3k`
- PaperChaser: `8706909962:AAFDukM98cnkjoUGR3tBS9qCPB_04U7sxws`
- Bot-Wave Trades: `8721939422:AAHkaabGThUbuJfIH_bWPcQPvgP5NeNK3p4`
- Bot-Wave Design: `8738524829:AAHQj7Td3ecK_0K8CgOe-zYGJjBHjBM7OIE`
- Captain Obvious: `8249528887:AAGjc386QGaG_-TJLkj3WOS03CYMqF0LOsc`
- Bot-Wave Business: `8611028472:AAEcrgEgg3oGYo_W6xcxCXGCJU2WpPruAFs`
- Deth1: `8649924686:AAEweJV0FoH-BnT95EV9Rf890eYPUxHawaM`

### Discord
- Bot Token: `MTQ4MDA2Nzk0OTIxMjQ3MTQ2OA...`
- Webhook: `https://discord.com/api/webhooks/1480066000...`

---

## 5. Critique Keeper Chain

Prompt template:
```
Input: {user_idea}
Step 1 (Strategy): Use xAI/Grok to draft strategy
Step 2 (Critique): Use Gemini to edit/refine
Step 3 (Polish): Use Ollama local to polish
Output: Final result with chain summary
```

Test via Telegram: Send `/critique` to Captain Obvious bot.

---

## 6. Network Diagnostics (Bambu Printer + OpenClaw Coexistence)

### Port Map (No Conflicts)
| Service | Port |
|---------|------|
| OpenClaw Gateway | 18789 |
| Ollama Local | 11434 |
| Bambu SSH | 22 |
| Bambu MQTT | 8883 |
| Bambu FTP | 990 |

### Debug Steps
```bash
# Check what's using key ports
sudo lsof -i :18789  # OpenClaw
sudo lsof -i :11434  # Ollama
sudo lsof -i :22     # SSH
sudo lsof -i :8883   # Bambu MQTT

# Find printer on network
nmap -sn 192.168.1.0/24  # Scan local network
arp -a | grep -i bamb   # Find Bambu MAC

# Test printer ports
nmap -p 22,8883,990 printer-ip  # Check open ports

# Test SSH to printer
ssh root@printer-ip -p 22 -v

# Test MQTT
mosquitto_pub -h printer-ip -p 8883 -t test -m "hello"
```

### Common Fixes
```bash
# Firewall check (allow ports)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 18789/tcp # OpenClaw
sudo ufw allow 8883/tcp  # Bambu MQTT
sudo ufw status

# If SSH refused: Enable Developer Mode on printer
# Settings > LAN Only Mode > Enable > Developer Mode

# If still no SSH: Enable Third Party Firmware Plan
# bambulab.com > Settings > Third Party Firmware Plan
```

### Dual SSH Access (Laptop + Printer)
```bash
# SSH to laptop (runs OpenClaw)
ssh user@laptop-ip

# From laptop, SSH to printer
ssh root@printer-ip

# Or direct (both on same network)
ssh user@192.168.1.100   # laptop
ssh root@192.168.1.101   # printer
```

---

## 7. System Optimization

```bash
# Kill unnecessary processes
ps aux --sort=-%mem | head -15
pkill -f chrome  # Close browser tabs
pkill -f spotify

# Free memory
sync && echo 3 | sudo tee /proc/sys/vm/drop_caches

# Check disk
df -h
docker system prune -af  # Clean Docker

# Ollama optimization
# Edit /etc/ollama.env for more RAM:
# OLLAMA_HOST=0.0.0.0:11434
# OLLAMA_NUM_PARALLEL=4
# OLLAMA_MAX_LOADED_MODELS=2
```

### Docker Deployment (Pi/Server)
```yaml
# docker-compose.yml
services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama:/root/.ollama
    deploy:
      resources:
        limits:
          memory: 16G

  openclaw:
    image: openclaw/openclaw:latest
    ports:
      - "18789:18789"
    environment:
      - OLLAMA_HOST=http://ollama:11434
    depends_on:
      - ollama

volumes:
  ollama:
```

Run: `docker-compose up -d`

---

## 8. Quick Commands

```bash
# Start Ollama
ollama serve &

# Check Ollama
curl http://localhost:11434/api/tags

# List models
ollama list

# OpenClaw status
ps aux | grep openclaw

# Restart OpenClaw
pkill openclaw && openclaw gateway --port 18789 --verbose
```

---

## 7. Network Diagnostics (Debug Port Conflicts/Access)

```bash
# Check all listening ports
sudo lsof -i -P -n | grep LISTEN

# Check specific port (e.g., 18789, 22, 8883)
sudo lsof -i :18789
sudo lsof -i :22
sudo lsof -i :8883

# Find your local IP
hostname -I | awk '{print $1}'

# Scan printer/network device ports
nmap -p 22,80,443,8883,990 printer-ip

# Test SSH to printer
ssh -v root@printer-ip -p 22

# Test MQTT (Bambu)
nc -zv printer-ip 8883

# Check firewall status
sudo ufw status          # Linux
sudo iptables -L         # Linux
# macOS: System Settings > Network > Firewall
```

### Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| SSH refused | Enable Developer Mode + Third Party Firmware Plan |
| Can't reach printer | Check same WiFi subnet |
| Port 18789 in use | `pkill openclaw` then restart |
| Ollama not responding | `ollama serve &` then `curl localhost:11434` |
| Bambu cloud disconnected | Normal in LAN Only mode |

---

## 8. Bambu Lab A1 Printer Integration

### Setup Steps
1. **Enable LAN Only Mode**: Printer touchscreen > Settings > WLAN > LAN Only Mode
2. **Enable Developer Mode**: Settings > Developer Mode (appears after LAN Only)
3. **Third Party Firmware Plan**: bambulab.com > Settings > Enable for your printer
4. **Get Root Password**: Printer > Settings > Third Party Firmware Plan > Enable root SSH

### Access
```bash
# SSH to printer (port 22)
ssh root@192.168.1.X  # Use printer IP from Settings > Network

# MQTT for automation (port 8883)
# Use paho-mqtt library for Botwave integration
```

### Ports Summary
| Service | Port |
|---------|------|
| OpenClaw Gateway | 18789 |
| Printer SSH | 22 |
| Printer MQTT | 8883 |
| Printer FTP | 990 |

---

## 9. System Optimization

```bash
# Check RAM usage
free -h

# Check disk I/O
iostat -x 1 5

# Kill idle processes
ps aux --sort=-%mem | head -10

# Auto-start Ollama on boot (Linux)
sudo systemctl enable ollama

# Auto-start OpenClaw
# Add to ~/.bashrc or use systemd
```

### Recommended Startup Script
```bash
#!/bin/bash
# botwave-start.sh
ollama serve &
sleep 2
openclaw gateway --port 18789 --verbose
```

---

## 10. Quick Commands

```bash
# Start Ollama
ollama serve &

# Check Ollama
curl http://localhost:11434/api/tags

# List models
ollama list

# OpenClaw status
ps aux | grep openclaw

# Restart OpenClaw
pkill openclaw && openclaw gateway --port 18789 --verbose
```

---

## 11. Future Expansion

- Add Pi/Docker compose deployment
- Full Critique Keeper skill code
- More Telegram bot agents
- GitHub integration for PR reviews
- Bambu printer automation via MQTT

---

*Last updated: 2026-03-08*
*Botwave Poor Man's Forge v2*

