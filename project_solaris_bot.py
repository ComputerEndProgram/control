# project_solaris_bot.py
# Starter template for Project: SOLARIS Discord Bot
# Implements core features: onboarding, verification, XP/leveling, promotions, /dossier
# Placeholders for moderation and immersive features
# Uses discord.py for Python implementation
# Modular structure with cogs for easy extension
# Database: SQLite for user XP and clearance levels
# Assumptions:
# - Role names match exactly as provided (e.g., "CL-0: Recruit")
# - Channel names match exactly (e.g., "#welcome", but use channel.name == 'welcome')
# - Bot token stored in environment variable or .env file (not included here)
# - Permissions for channels are set via Discord role overrides (bot only manages role assignments)
# - XP system: Simple +1 XP per message, thresholds increase exponentially (customizable)
# - Verification: Reaction to a specific message in #verification channel

import discord
from discord.ext import commands
import sqlite3
import os
import asyncio
from dotenv import load_dotenv  # Optional: For loading .env file

# Load environment variables (e.g., bot token)
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Bot setup
intents = discord.Intents.default()
intents.members = True  # Needed for on_member_join
intents.message_content = True  # Needed for on_message XP
bot = commands.Bot(command_prefix='!', intents=intents, application_id=YOUR_APP_ID_HERE)  # Replace with your bot's app ID for slash commands

# Database setup
DB_FILE = 'solaris.db'
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        xp INTEGER DEFAULT 0,
        clearance_level INTEGER DEFAULT 0
    )
''')
conn.commit()

# Clearance levels and role names
CLEARANCE_ROLES = {
    0: 'CL-0: Recruit',
    1: 'CL-1: Initiate',
    2: 'CL-2: Asset',
    3: 'CL-3: Agent',
    4: 'CL-4: Field Agent',
    5: 'CL-5: Senior Agent',
    6: 'CL-6: Special Operative',
    7: 'CL-7: Handler',
    8: 'CL-8: Intelligence Officer',
    9: 'CL-9: Shadow Commander',
    10: 'CL-10: Control'
}

# XP thresholds for promotions (example: exponential growth, adjust as needed)
XP_THRESHOLDS = [0, 100, 300, 600, 1000, 1500, 2100, 2800, 3600, 4500, 5500]  # Index corresponds to next level

# Helper functions
def get_user_data(user_id):
    cursor.execute('SELECT xp, clearance_level FROM users WHERE user_id = ?', (user_id,))
    return cursor.fetchone() or (0, 0)

def update_user_data(user_id, xp, level):
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, xp, clearance_level)
        VALUES (?, ?, ?)
    ''', (user_id, xp, level))
    conn.commit()

async def promote_user(member, new_level, guild):
    # Remove lower clearance roles
    for level in range(0, new_level):
        role_name = CLEARANCE_ROLES.get(level)
        if role_name:
            role = discord.utils.get(guild.roles, name=role_name)
            if role and role in member.roles:
                await member.remove_roles(role)
    
    # Add new role
    new_role_name = CLEARANCE_ROLES.get(new_level)
    if new_role_name:
        new_role = discord.utils.get(guild.roles, name=new_role_name)
        if new_role:
            await member.add_roles(new_role)
    
    # Announce promotion
    announcements_channel = discord.utils.get(guild.text_channels, name='announcements')
    if announcements_channel:
        await announcements_channel.send(f"**Promotion Alert:** {member.mention} has been elevated to {new_role_name}!")

# Cog for Onboarding and Verification
class OnboardingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.verification_message_id = None  # To store the ID of the verification message

    @commands.Cog.listener()
    async def on_member_join(self, member):
        # Assign CL-0: Recruit role
        guild = member.guild
        recruit_role = discord.utils.get(guild.roles, name=CLEARANCE_ROLES[0])
        if recruit_role:
            await member.add_roles(recruit_role)
        
        # Update DB
        update_user_data(member.id, 0, 0)
        
        # DM welcome message with Directive 01
        welcome_msg = (
            "Welcome to Project: SOLARIS, Recruit.\n\n"
            "**Directive 01:** Report to #verification for clearance processing. "
            "Section 31 protocols are now in effect. Discretion is mandatory."
        )
        try:
            await member.send(welcome_msg)
        except discord.Forbidden:
            pass  # User has DMs disabled
        
        # Send verification message if not already sent
        verification_channel = discord.utils.get(guild.text_channels, name='verification')
        if verification_channel and not self.verification_message_id:
            msg = await verification_channel.send(
                "React with ✅ to verify and gain CL-1: Initiate clearance."
            )
            await msg.add_reaction('✅')
            self.verification_message_id = msg.id

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.message_id != self.verification_message_id:
            return
        if str(payload.emoji) != '✅':
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        if member and member.bot:
            return
        
        # Promote to CL-1 if currently CL-0
        _, current_level = get_user_data(payload.user_id)
        if current_level == 0:
            update_user_data(payload.user_id, 0, 1)
            await promote_user(member, 1, guild)

# Cog for Leveling and Promotions
class LevelingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        
        # Add XP (simple: +1 per message, adjust for activity)
        xp, level = get_user_data(message.author.id)
        xp += 1
        update_user_data(message.author.id, xp, level)
        
        # Check for promotion
        if level < 10:
            next_threshold = XP_THRESHOLDS[level + 1]
            if xp >= next_threshold:
                new_level = level + 1
                update_user_data(message.author.id, xp, new_level)
                await promote_user(message.author, new_level, message.guild)
        
        # Process commands if any
        await self.bot.process_commands(message)

# Cog for Commands (e.g., /dossier)
class CommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name='dossier', description='Display user XP, CL, and rank')
    @discord.app_commands.describe(user='The user to check (defaults to yourself)')
    async def dossier(self, interaction: discord.Interaction, user: discord.Member = None):
        if user is None:
            user = interaction.user
        
        xp, level = get_user_data(user.id)
        role_name = CLEARANCE_ROLES.get(level, 'Unknown')
        
        embed = discord.Embed(title=f"Dossier: {user.display_name}", color=discord.Color.dark_blue())
        embed.add_field(name="Clearance Level", value=f"CL-{level}", inline=True)
        embed.add_field(name="Rank", value=role_name, inline=True)
        embed.add_field(name="XP", value=xp, inline=True)
        
        # Supports DMs (ephemeral if in server)
        await interaction.response.send_message(embed=embed, ephemeral=bool(interaction.guild))

# Placeholder Cog for Moderation Tools
class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # TODO: Implement kick, ban, mute, warn commands
        # TODO: Auto-moderation listeners (e.g., on_message for bad words/spam)
        # TODO: Log to #ops-logs
        # Note: Integrate with Discord's Automod API if needed via bot interactions

    # Example placeholder command
    @commands.command(name='warn')
    @commands.has_permissions(manage_messages=True)  # Or check CL-9/CL-10
    async def warn(self, ctx, member: discord.Member, *, reason=None):
        # Placeholder
        await ctx.send(f"Warning {member.mention} for {reason}. (Implement logging and actions)")

# Placeholder Cog for Immersive Features
class ImmersiveCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # TODO: /mission to generate random objectives
        # TODO: /encrypt [text] for ciphered output
        # TODO: Thematic greetings, random intel drops

    # Example placeholder slash command (works in DMs)
    @discord.app_commands.command(name='mission', description='Generate a random mission')
    async def mission(self, interaction: discord.Interaction):
        # Placeholder
        await interaction.response.send_message("Mission: Infiltrate target. (Implement generation logic)")

# Bot setup and run
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    # Sync slash commands globally for DM support
    await bot.tree.sync()
    # Bot identity
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Agent Activity"))
    # Note: Set bot name via Discord dev portal: "CONTROL" or "S31-Core"

# Add cogs
async def setup_bot():
    await bot.add_cog(OnboardingCog(bot))
    await bot.add_cog(LevelingCog(bot))
    await bot.add_cog(CommandsCog(bot))
    await bot.add_cog(ModerationCog(bot))
    await bot.add_cog(ImmersiveCog(bot))

asyncio.run(setup_bot())
bot.run(TOKEN)

# To extend:
# - Add more commands to cogs
# - Adjust XP logic (e.g., cooldowns, multipliers)
# - Implement full moderation (use discord.py's moderation extensions if available)
# - For events/side missions: Use tasks or listeners
# - For Automod integration: Bot can react to Automod events if webhooks set up
