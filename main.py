# main.py

import asyncio
from datetime import datetime, timedelta
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from keep_alive import keep_alive
from handlers import handle_verification
# NEW: global block helpers (set by utils.safe_send on 429/1015)
from utils import is_globally_blocked, get_block_remaining_seconds

# Load .env values
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

# Roles
BLOCKED_ROLE = "verified"
ALLOWED_ROLES = ["unverified", "mod"]

# Channels
WELCOME_CHANNEL_NAME = "start-here-for-verification"

# Setup bot
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Concurrency/anti-spam controls
last_verification_time = None
verification_lock = asyncio.Lock()

@bot.event
async def on_ready():
    print(f"{bot.user} is now running!")

@bot.command()
@commands.cooldown(1, 120, commands.BucketType.user)  # per-user 2-minute cooldown
async def verifyme(ctx):
    global last_verification_time

    # Ignore DMs
    if not ctx.guild:
        return

    # Must be in the designated channel
    if ctx.channel.name != WELCOME_CHANNEL_NAME:
        await ctx.send("Please use the designated channel for verification.")
        return

    # NEW: respect global cool-down if we recently hit 429/1015
    if is_globally_blocked():
        secs = get_block_remaining_seconds()
        mins = max(1, secs // 60)
        await ctx.send(f"Bot is cooling down due to rate limits. Please try again in ~{mins} minute(s).")
        return

    # Small global burst throttle (protects against many simultaneous starts)
    async with verification_lock:
        now = datetime.utcnow()
        if last_verification_time and (now - last_verification_time) < timedelta(seconds=10):
            await ctx.send("Too many users are verifying right now. Please wait a few seconds and try again.")
            return
        last_verification_time = now

    member = ctx.author
    roles = [role.name.lower() for role in member.roles]

    # Access control
    if "mod" in roles:
        pass
    elif "unverified" in roles and BLOCKED_ROLE not in roles:
        pass
    elif BLOCKED_ROLE in roles and "mod" not in roles:
        await ctx.send("You are already verified and cannot take the quiz again.")
        return
    else:
        await ctx.send("You are not permitted to take the verification quiz.")
        return

    # Start the verification flow (DM quiz)
    await handle_verification(ctx, bot, GUILD_ID, WELCOME_CHANNEL_NAME, None, None)

# Optional: nicer error for command cooldown so logs don’t spam
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        retry_in = int(error.retry_after)
        mins = max(1, retry_in // 60)
        await ctx.send(f"You're on cooldown for this command. Please try again in ~{mins} minute(s).")
    else:
        # Leave other errors to default logging
        raise error

# Keep-alive (for Render ping)
keep_alive()
bot.run(TOKEN)