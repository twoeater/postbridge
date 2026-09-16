# systemd samples

These unit files assume the following example layout:

```text
/opt/postbridge              application source and virtualenv
/etc/postbridge/.env         shared environment file
/var/lib/postbridge          writable DB, posts, and runtime state
```

They also assume a dedicated `postbridge` system user and group. Before enabling the units, prepare the Python virtual environment and build the MCP server if you plan to use it:

```bash
cd /opt/postbridge
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cd /opt/postbridge/mcp
npm install
npm run build
```

Example user/directory preparation:

```bash
sudo useradd --system --home /var/lib/postbridge --shell /usr/sbin/nologin postbridge
sudo install -d -o postbridge -g postbridge -m 0750 /var/lib/postbridge
sudo install -d -o root -g postbridge -m 0750 /etc/postbridge
sudo chown -R root:postbridge /opt/postbridge
sudo chmod -R g+rX /opt/postbridge
sudo chown root:postbridge /etc/postbridge/.env
sudo chmod 0640 /etc/postbridge/.env
```

Install the units:

```bash
sudo cp scripts/systemd/postbridge*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now postbridge.service
```

Enable the optional publishers when configured:

```bash
sudo systemctl enable --now postbridge-mcp.service
sudo systemctl enable --now postbridge-ntfy.service
```

The MCP sample expects Node.js at `/usr/bin/node`. Change `ExecStart` if Node.js is installed elsewhere.
