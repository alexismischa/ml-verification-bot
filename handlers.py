import discord
import random
import asyncio
import time
import os
import json
from datetime import datetime

from utils import (
    can_attempt_quiz,
    record_attempt,
    get_remaining_attempts,
    get_role_names,
    safe_send,
    increment_failure_count,
    get_failure_count
)
from quiz import get_questions

active_quiz_users = set()
MAX_CONCURRENT_QUIZZES = 5
user_cooldowns = {}
QUIZ_COOLDOWN_SECONDS = 120


# NEW: Local logger for answers -> answer-logs/<username>.json
def log_quiz_answers_local(username: str, qa_records: list):
    """
    Append one quiz attempt to answer-logs/<username>.json

    username: e.g. 'Name#1234'
    qa_records: list of dicts like:
        { "question": "...", "answer": "...", "points": 5 }
    """
    log_dir = "answer-logs"
    os.makedirs(log_dir, exist_ok=True)

    # Make a safe filename
    safe_username = "".join(c for c in username if c.isalnum() or c in (' ', '_', '-', '#')).rstrip()
    log_path = os.path.join(log_dir, f"{safe_username}.json")

    attempt = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "entries": qa_records
    }

    # Load existing (if any), append, save
    data = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            # If somehow corrupted, start fresh list
            data = []

    data.append(attempt)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[LOCAL LOG] Saved quiz answers for {username} -> {log_path}")


async def handle_verification(ctx, bot, guild_id, welcome_channel_name, answer_log_category, answer_log_channel):
    member = ctx.author
    roles = get_role_names(member)

    now = time.time()
    last_time = user_cooldowns.get(member.id, 0)
    if now - last_time < QUIZ_COOLDOWN_SECONDS:
        await safe_send(ctx, f"You can only start a quiz every {QUIZ_COOLDOWN_SECONDS // 60} minutes. Please wait.")
        return
    user_cooldowns[member.id] = now

    if "mod" in roles:
        pass
    elif "unverified" in roles and "verified" not in roles:
        pass
    elif "verified" in roles and "mod" not in roles:
        await safe_send(ctx, "You are already verified and cannot take the quiz again.")
        return
    else:
        await safe_send(ctx, "You are not permitted to take the verification quiz.")
        return

    if not can_attempt_quiz(member.id):
        await safe_send(ctx, "You have reached the maximum number of quiz attempts (4).")
        return

    if member.id in active_quiz_users:
        await safe_send(ctx, "You're already in a quiz session.")
        return

    if len(active_quiz_users) >= MAX_CONCURRENT_QUIZZES:
        await safe_send(ctx, "Too many users are currently taking the quiz. Please wait a moment and try again.")
        return

    active_quiz_users.add(member.id)

    # DM availability check — no extra test message
    try:
        dm_channel = await member.create_dm()
    except discord.Forbidden:
        await safe_send(ctx, "I couldn't DM you. Please enable DMs and try again.")
        active_quiz_users.discard(member.id)
        return

    await asyncio.sleep(random.uniform(1.0, 2.5))  # burst smoothing

    intro = (
        "Hello there, my cutesy comrade! You're about to begin a short quiz for a vibe check! "
        "You'll need 30/40 to pass. Answer with A, B, C, or D (No periods/full-stops, only letters). You’ve got this - and we're rooting for you!"
    )
    if not await safe_send(dm_channel, intro):
        await safe_send(ctx, "I couldn't DM you. Please enable DMs and try again.")
        active_quiz_users.discard(member.id)
        return

    score = 0
    questions = get_questions()

    # NEW: keep local records so we can log to disk later
    qa_records = []  # list of dicts {question, answer, points}

    for idx, q in enumerate(questions, 1):
        options = q["options"]
        letters = list(options.keys())
        formatted_options = "\n".join(f"{letter}. {options[letter][0]}" for letter in letters)
        question_text = f"**{q['question']}**\n{formatted_options}"

        await asyncio.sleep(1.0)  # 1s between DMs

        if not await safe_send(dm_channel, question_text):
            increment_failure_count()
            await safe_send(ctx, "Something went wrong sending you quiz questions. Try again later.")
            active_quiz_users.discard(member.id)
            return

        def check(m):
            return m.author == member and m.channel == dm_channel

        try:
            msg = await bot.wait_for("message", check=check, timeout=300)
        except asyncio.TimeoutError:
            await safe_send(dm_channel, "Oh no! Time's up! Try again later when you're ready, ok?")
            active_quiz_users.discard(member.id)
            return

        answer_letter = msg.content.strip().upper()
        if answer_letter in letters:
            selected_text, pts = options[answer_letter][0], options[answer_letter][1]
            score += pts
            # NEW: record per-question answer for local log
            qa_records.append({
                "question": q["question"],
                "answer": selected_text,
                "points": pts
            })
        else:
            await safe_send(dm_channel, "Oopsies! That wasn’t one of the options. Let's skip this one for now!")
            # NEW: record invalid as well
            qa_records.append({
                "question": q["question"],
                "answer": f"Invalid/Skipped: {msg.content.strip()}",
                "points": 0
            })

    # NEW: local disk log (no Discord API traffic)
    try:
        log_quiz_answers_local(f"{member.name}#{member.discriminator}", qa_records)
    except Exception as e:
        # Never crash quiz flow due to local IO
        print(f"[LOCAL LOG ERROR] {e}")

    record_attempt(member.id)

    if score >= 30:
        verified_role = discord.utils.get(member.guild.roles, name="verified")
        unverified_role = discord.utils.get(member.guild.roles, name="unverified")
        if verified_role:
            if unverified_role and unverified_role in member.roles:
                await member.remove_roles(unverified_role)
                await asyncio.sleep(1.0)  # delay before adding role
            await member.add_roles(verified_role)
            await safe_send(dm_channel, f"Yippee! You passed with {score}/40. Welcome to our little corner of summer and sunshine - and don't forget to read the rules at #rules-and-etiquettes before you jump. Welcome, and we can't wait to get to know you!")
        else:
            await safe_send(dm_channel, "You passed the quiz, but I couldn't find the **verified** role to assign you.")
    else:
        remaining = get_remaining_attempts(member.id)
        await safe_send(dm_channel,
            f"Uh oh, sorry but you scored {score}/40. Sadly, that's not quite enough to align with our ideological positions. "
            f"But don’t worry — you can try again! Second time's the charm! Or third? Maybe fourth....? You can try again by typing the command in the earlier channel. Best of luck!\n"
            f"You have {remaining} attempt(s) left!"
        )

    await asyncio.sleep(1.0)
    log_channel = discord.utils.get(ctx.guild.text_channels, name="user-answers")
    if log_channel:
        # Keep Discord log minimal to avoid rate/size issues
        await safe_send(log_channel, f"User: {member.name}#{member.discriminator} — Final Score: {score}/40")

        if get_failure_count() > 5:
            await safe_send(log_channel, "Alert: High number of recent failed message sends. Check rate limits or bot health.")

    active_quiz_users.discard(member.id)