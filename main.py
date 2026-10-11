# language: Python, file: main.py, target: Render Web Service
import os
import urllib.parse
import urllib.request
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import discord
from discord.ext import commands

CLIENT_ID = os.getenv("CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GUILD_ID = os.getenv("GUILD_ID", "")
INVITE_CODE = os.getenv("INVITE_CODE", "").strip()
PORT = int(os.getenv("PORT", 5000))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", f"http://localhost:{PORT}")
REDIRECT_URI = f"{RENDER_EXTERNAL_URL}/callback"

if not BOT_TOKEN:
    print("[!] ERROR: BOT_TOKEN environment variable is not set in Render dashboard.")
    exit(1)

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

def resolve_guild_id():
    if GUILD_ID:
        return GUILD_ID
    if not INVITE_CODE:
        print("[!] ERROR: INVITE_CODE or GUILD_ID environment variable is missing.")
        return None
    url = f"https://discord.com/api/v10/invites/{INVITE_CODE}?with_counts=false"
    req = urllib.request.Request(url, headers={"Authorization": f"Bot {BOT_TOKEN}"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return data.get("guild", {}).get("id")
    except Exception as e:
        print(f"[!] Error resolving invite '{INVITE_CODE}': {e}. Set GUILD_ID directly in Render environment variables if invite lookup fails.")
        return None

RESOLVED_GUILD_ID = resolve_guild_id()

class OAuthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            scope = "identify guilds.join"
            auth_url = (
                f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}"
                f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}&response_type=code&scope={scope}"
            )
            html = f'<h2>MasterDev Portal</h2><p>Target Invite: discord.gg/{INVITE_CODE}</p><a href="{auth_url}">Authorize & Join Server</a>'.encode()
            self.wfile.write(html)
        elif parsed.path == "/callback":
            query = urllib.parse.parse_qs(parsed.query)
            code = query.get("code", [None])[0]
            if not code:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Authorization failed.")
                return

            data = urllib.parse.urlencode({
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI
            }).encode()

            req = urllib.request.Request(
                "https://discord.com/api/oauth2/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    res_json = json.loads(resp.read().decode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Token exchange failed: {e}".encode())
                return

            access_token = res_json.get("access_token")
            user_req = urllib.request.Request(
                "https://discord.com/api/users/@me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            with urllib.request.urlopen(user_req) as user_resp:
                user_data = json.loads(user_resp.read().decode())
                user_id = user_data.get("id")

            add_url = f"https://discord.com/api/v10/guilds/{RESOLVED_GUILD_ID}/members/{user_id}"
            add_data = json.dumps({"access_token": access_token}).encode()
            add_req = urllib.request.Request(
                add_url,
                data=add_data,
                headers={
                    "Authorization": f"Bot {BOT_TOKEN}",
                    "Content-Type": "application/json"
                },
                method="PUT"
            )
            try:
                with urllib.request.urlopen(add_req) as add_resp:
                    if add_resp.status in [201, 204]:
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b"Success! You have been added to the target server.")
                        return
            except urllib.error.HTTPError as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Guild add error: {e.read().decode()}".encode())
                return

def run_server():
    server = HTTPServer(("0.0.0.0", PORT), OAuthHandler)
    server.serve_forever()

@bot.event
async def on_ready():
    print(f"Bot active: {bot.user.name}")

if __name__ == "__main__":
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    bot.run(BOT_TOKEN)