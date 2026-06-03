# Deployment Guide: Research Assistant on EC2

## Overview

This guide covers deploying the Research Assistant as a containerized service on AWS EC2 with Dynatrace observability.

**Target environment:** EC2 t3.micro instance (Ubuntu 22.04 LTS), ~$5-10/month

---

## Prerequisites

1. **AWS Account** with EC2 access
2. **OpenAI API Key** (from https://platform.openai.com/api-keys)
3. **Dynatrace environment** (optional, but recommended for observability)
   - Base OTLP endpoint: `https://<env>.live.dynatrace.com/api/v2/otlp`
   - API token with `openTelemetryTrace.ingest` and `metrics.ingest` scopes

---

## Step 1: Launch EC2 Instance

1. **Go to AWS Console → EC2 → Instances → Launch Instances**

2. **Configure instance:**
   - **AMI**: Ubuntu 22.04 LTS (free tier eligible)
   - **Instance type**: `t3.micro` (free tier eligible; $5-10/month after free tier)
   - **Key Pair**: Create or select an existing key pair (needed for SSH)
   - **Security group**:
     - Inbound: SSH (22) from your IP, HTTP (80) from anywhere, HTTPS (443) from anywhere
     - Outbound: Allow all (default)
   - **Storage**: 20 GB gp3 (default is fine)
   - **IAM instance profile**: None required (optional for CloudWatch logging)

3. **Launch** and wait for instance to start (1-2 minutes)

---

## Step 2: SSH into Instance

```bash
# Replace with your instance IP and key file
ssh -i /path/to/key.pem ubuntu@<instance-ip>
```

---

## Step 3: Install Docker

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Docker
sudo apt install -y docker.io

# Add ubuntu user to docker group (allows running docker without sudo)
sudo usermod -aG docker ubuntu

# Verify installation (may need to logout/login or use newgrp)
docker --version
```

---

## Step 4: Clone Repository

```bash
# Clone the repository
git clone https://github.com/russel.wilkinson/research-assistant.git ~/research-assistant
cd ~/research-assistant
```

---

## Step 5: Create Environment File

```bash
# Create .env file with your credentials (never commit to git)
cat > /home/ubuntu/research-assistant/.env << 'EOF'
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-3.5-turbo
LOG_LEVEL=INFO
DT_API_URL=https://<your-env>.live.dynatrace.com/api/v2/otlp
DT_API_TOKEN=your_dynatrace_api_token_here
EOF

# Restrict permissions (important!)
chmod 600 /home/ubuntu/research-assistant/.env

# Verify (should show only .env, no content)
ls -la .env
```

---

## Step 6: Build Docker Image

```bash
cd ~/research-assistant

# Build the Docker image
docker build -t research-assistant:latest .

# Verify build (should see "Successfully tagged")
docker images | grep research-assistant
```

---

## Step 7: Test Docker Container Locally

```bash
# Run the container with test env vars
docker run --rm \
  -e OPENAI_API_KEY="sk-test" \
  -e LOG_LEVEL="INFO" \
  -p 8000:8000 \
  research-assistant:latest &

# Wait 5 seconds for startup
sleep 5

# Test health endpoint
curl http://localhost:8000/health

# You should see: {"status":"ok","sessions_active":0}

# Stop container (Ctrl+C or kill the process)
```

---

## Step 8: Create Systemd Service

```bash
# Create systemd unit file
sudo tee /etc/systemd/system/research-assistant.service > /dev/null << 'EOF'
[Unit]
Description=Research Assistant HTTP Service
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/research-assistant
EnvironmentFile=/home/ubuntu/research-assistant/.env
ExecStart=/usr/bin/docker run --rm \
  --name research-assistant \
  -e OPENAI_API_KEY=${OPENAI_API_KEY} \
  -e OPENAI_MODEL=${OPENAI_MODEL} \
  -e LOG_LEVEL=${LOG_LEVEL} \
  -e DT_API_URL=${DT_API_URL} \
  -e DT_API_TOKEN=${DT_API_TOKEN} \
  -p 8000:8000 \
  research-assistant:latest
Restart=unless-stopped
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

# Enable service (starts on boot)
sudo systemctl enable research-assistant

# Start service
sudo systemctl start research-assistant

# Check status
sudo systemctl status research-assistant
```

---

## Step 9: Verify Service

```bash
# Check service status
sudo systemctl status research-assistant

# View logs
sudo journalctl -u research-assistant -f

# Test API endpoint
curl http://localhost:8000/health
curl http://localhost:8000/

# Test chat endpoint
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What is Python?"}' | jq .

# View structured logs
sudo journalctl -u research-assistant -n 20 | grep '"level"'
```

---

## Step 10: Configure Nginx (Optional but Recommended)

If you want HTTPS, domain support, or static frontend serving:

```bash
# Install Nginx and Certbot
sudo apt install -y nginx certbot python3-certbot-nginx

# Create Nginx configuration
sudo tee /etc/nginx/sites-available/research-assistant > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

    # Frontend static files
    root /home/ubuntu/research-assistant/public;
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxy
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
    }

    # Health check
    location /health {
        proxy_pass http://localhost:8000;
    }

    # API documentation
    location /docs {
        proxy_pass http://localhost:8000;
    }

    location /openapi.json {
        proxy_pass http://localhost:8000;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/research-assistant /etc/nginx/sites-enabled/

# Remove default site
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx

# Verify (should see Nginx welcome or redirect)
curl http://localhost/
```

### Optional: HTTPS with Let's Encrypt

```bash
# If you have a domain, use certbot to set up HTTPS
sudo certbot --nginx -d your-domain.com

# Certbot will automatically update Nginx config
# HTTPS will be enabled and auto-renewed
```

---

## Verification Checklist

- [ ] Instance is running and SSH accessible
- [ ] Docker is installed
- [ ] Repository is cloned
- [ ] `.env` file is created with credentials (not world-readable)
- [ ] Docker image builds without errors
- [ ] Service starts and is healthy: `sudo systemctl status research-assistant`
- [ ] Health endpoint responds: `curl http://localhost:8000/health`
- [ ] API endpoint works: `curl -X POST http://localhost:8000/api/chat -d '{"message":"test"}'`
- [ ] Logs appear as JSON: `sudo journalctl -u research-assistant | grep '"level"'`
- [ ] Dynatrace shows service (if configured)
- [ ] Nginx proxies correctly (if installed)
- [ ] Frontend loads: `curl http://localhost/`

---

## Troubleshooting

### Service won't start
```bash
# Check logs for errors
sudo journalctl -u research-assistant -n 50

# Check Docker logs
docker logs research-assistant

# Verify .env file exists and has correct permissions
ls -la /home/ubuntu/research-assistant/.env
```

### Health check fails
```bash
# Check if container is running
docker ps | grep research-assistant

# Check if port 8000 is listening
netstat -tlnp | grep 8000

# Manually test health endpoint
docker exec research-assistant curl http://localhost:8000/health
```

### Tracing not appearing in Dynatrace
```bash
# Verify env vars are set
grep DT_API /home/ubuntu/research-assistant/.env

# Check logs for tracing initialization
sudo journalctl -u research-assistant | grep -i "tracing"

# Send a test request and check Dynatrace UI
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"test"}'
```

### Container crashes on startup
```bash
# Check Docker build output for Python dependency errors
docker build -t research-assistant:latest .

# Verify requirements.txt has all dependencies
cat requirements.txt

# Check for syntax errors in app.py
docker run --rm research-assistant:latest python -m py_compile app.py
```

---

## Accessing the Service

**Without Nginx:**
- API: `http://<instance-ip>:8000/api/chat`
- Health: `http://<instance-ip>:8000/health`
- Docs: `http://<instance-ip>:8000/docs`

**With Nginx:**
- Frontend: `http://<instance-ip>/`
- API: `http://<instance-ip>/api/chat` (proxied to :8000)
- Health: `http://<instance-ip>/health`
- Docs: `http://<instance-ip>/docs`

**With Nginx + HTTPS:**
- Frontend: `https://<your-domain>/`
- API: `https://<your-domain>/api/chat`

---

## Monitoring

### Logs
```bash
# Real-time logs
sudo journalctl -u research-assistant -f

# Last 50 lines
sudo journalctl -u research-assistant -n 50

# Filter by log level
sudo journalctl -u research-assistant --grep=ERROR

# View structured JSON logs
sudo journalctl -u research-assistant -o json-pretty | head -100
```

### Dynatrace
1. Navigate to Dynatrace UI
2. Go to **Services** → Find "research-assistant-api"
3. View **Spans**, **Metrics**, **Errors**
4. Check **OpenAI** spans for token counts and latency

### Resource Usage
```bash
# Check EC2 instance resource usage
free -h  # Memory
df -h    # Disk
top      # CPU
```

---

## Updates & Maintenance

### Update Code
```bash
cd ~/research-assistant
git pull origin main
docker build -t research-assistant:latest .
sudo systemctl restart research-assistant
```

### Update Dependencies
```bash
# Edit requirements.txt with new versions
nano requirements.txt

# Rebuild image
docker build -t research-assistant:latest .

# Restart service
sudo systemctl restart research-assistant
```

### Rotate Secrets
```bash
# Edit .env with new credentials
sudo nano /home/ubuntu/research-assistant/.env

# Restart service to pick up new env vars
sudo systemctl restart research-assistant
```

---

## Security Notes

- **`.env` file**: Never commit to git; use `.env.example` as template
- **Permissions**: Keep `.env` readable only by ubuntu user (600)
- **IP filtering**: Restrict SSH (port 22) to your IP in security group
- **HTTPS**: Use Nginx + Let's Encrypt for production
- **API tokens**: Rotate credentials regularly
- **Logs**: Structured JSON logs; avoid logging sensitive data (already handled)

---

## Cost Estimation

| Resource | Monthly Cost |
|----------|-------------|
| EC2 t3.micro | $5-10 |
| EBS 20GB | ~$2 |
| Data transfer | ~$0 (light traffic) |
| **Total** | **~$7-12** |

*Pricing may vary by region; free tier available for 12 months for new AWS accounts.*

---

## Support

For issues, check:
1. Logs: `sudo journalctl -u research-assistant -f`
2. Docker logs: `docker logs research-assistant`
3. Dynatrace dashboard: Check for errors and latency spikes
4. GitHub repository: Issues and discussions

---

## Next Steps

1. **Monitor in production**: Watch logs and Dynatrace for errors
2. **Test with real queries**: Verify accuracy and response quality
3. **Optimize**: Adjust timeouts, model, or tools as needed
4. **Scale**: If needed, consider Fargate or ECS with load balancer

---

**Deployment complete! The Research Assistant is now live on your EC2 instance.**
