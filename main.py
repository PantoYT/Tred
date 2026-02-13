import discord
from discord.ext import commands
from dotenv import load_dotenv
import json
import os
from datetime import datetime
import pathlib
import hashlib
import re
import asyncio
import random

# -------------------------------
# Load environment
# -------------------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
TRIVIA_FILE = pathlib.Path(__file__).parent / "trivia.json"

# -------------------------------
# Discord bot setup
# -------------------------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

# Rave mode state
rave_mode_active = False
rave_task = None
annoy_user_id = None

# -------------------------------
# Helper functions
# -------------------------------
def load_trivia():
    if TRIVIA_FILE.exists():
        try:
            with open(TRIVIA_FILE, "r", encoding="utf-8") as f:
                trivia_list = json.load(f)
                needs_save = False
                next_id = max([t.get("id", 0) for t in trivia_list], default=0) + 1
                for t in trivia_list:
                    if "id" not in t:
                        t["id"] = next_id
                        next_id += 1
                        needs_save = True
                if needs_save:
                    save_trivia(trivia_list)
                return trivia_list
        except json.JSONDecodeError as e:
            print(f"Error loading trivia: {e}")
            return []
    return []

def save_trivia(trivia_list):
    try:
        with open(TRIVIA_FILE, "w", encoding="utf-8") as f:
            json.dump(trivia_list, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving trivia: {e}")

def get_next_id(trivia_list):
    if not trivia_list:
        return 1
    return max([t.get("id", 0) for t in trivia_list]) + 1

def find_trivia_by_id(trivia_list, trivia_id):
    for t in trivia_list:
        if t.get("id") == trivia_id:
            return t
    return None

def format_category_name(name):
    return name.strip()

def categorize_contributor(count):
    if count <= 5:
        return "Trivia Novice"
    elif count <= 15:
        return "Fact Finder"
    elif count <= 30:
        return "Knowledge Seeker"
    elif count <= 50:
        return "Trivia Expert"
    elif count <= 75:
        return "Fact Master"
    elif count <= 100:
        return "Encyclopedia"
    else:
        return "Omniscient"

def clean_trivia_text(text):
    """Remove Discord mentions and clean text for status"""
    # Remove user mentions <@123456789> or <@!123456789>
    text = re.sub(r'<@!?\d+>', '', text)
    # Remove role mentions <@&123456789>
    text = re.sub(r'<@&\d+>', '', text)
    # Remove channel mentions <#123456789>
    text = re.sub(r'<#\d+>', '', text)
    # Clean up extra spaces
    text = ' '.join(text.split())
    return text.strip()

def get_daily_trivia_index(trivia_list):
    if not trivia_list:
        return 0
    
    today = datetime.now().strftime("%Y-%m-%d")
    hash_obj = hashlib.md5(today.encode())
    hash_int = int(hash_obj.hexdigest(), 16)
    
    return hash_int % len(trivia_list)

def can_modify_trivia(interaction, trivia, owner_id):
    """Check if user can modify this trivia"""
    if interaction.user.id == owner_id:
        return True
    
    return interaction.user.name == trivia.get("contributor", "")

def get_valid_status_trivia(trivia_list):
    """Filter trivia that fit in status (max 128 chars after cleaning)"""
    valid = []
    for t in trivia_list:
        cleaned_text = clean_trivia_text(t["text"])
        status_text = f'Did you know? {cleaned_text}'
        if len(status_text) <= 128:
            valid.append(t)
    return valid

async def set_status_to_trivia(trivia):
    """Set bot status to a specific trivia"""
    cleaned_text = clean_trivia_text(trivia["text"])
    status_text = f'Did you know? {cleaned_text}'
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=status_text
        )
    )
    print(f"Status set to: {status_text}")

def format_rave_message(trivia):
    """Format trivia message for rave mode (simple text, no embeds)"""
    category = trivia.get("category", "General")
    return f'**RAVE MODE** 🎉\nDid you know? {trivia["text"]} (Category: {category}, #{trivia["id"]})'

async def rave_mode_loop(channel_to_spam=None):
    """Main rave mode loop - cycles trivia every 5 seconds"""
    global rave_mode_active, annoy_user_id
    
    trivia_list = load_trivia()
    valid_trivia = get_valid_status_trivia(trivia_list)
    
    if not valid_trivia:
        valid_trivia = trivia_list  # Fallback to all trivia
    
    index = 0
    
    while rave_mode_active:
        try:
            trivia = valid_trivia[index % len(valid_trivia)]
            
            # Update status
            await set_status_to_trivia(trivia)
            
            # Send message to channel if provided
            if channel_to_spam:
                message_text = format_rave_message(trivia)
                
                # Add ping if set
                if annoy_user_id == "everyone":
                    message_text = f"@everyone\n{message_text}"
                elif annoy_user_id:
                    message_text = f"<@{annoy_user_id}>\n{message_text}"
                
                await channel_to_spam.send(message_text)
            
            index += 1
            await asyncio.sleep(5)
            
        except Exception as e:
            print(f"Rave mode error: {e}")
            await asyncio.sleep(5)

# -------------------------------
# Events
# -------------------------------
@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    
    # List all registered commands BEFORE sync
    print(f"Commands registered: {[cmd.name for cmd in bot.tree.get_commands()]}")
    
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
        print(f"Command names: {[cmd.name for cmd in synced]}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    
    trivia_list = load_trivia()
    if trivia_list:
        valid_trivia = get_valid_status_trivia(trivia_list)
        
        if valid_trivia:
            index = get_daily_trivia_index(valid_trivia)
            daily_trivia = valid_trivia[index]
            await set_status_to_trivia(daily_trivia)
        else:
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="Tracking trivia & funfacts | /commands"
                )
            )
    else:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Tracking trivia & funfacts | /commands"
            )
        )

# -------------------------------
# Commands
# -------------------------------
@bot.tree.command(name="commands", description="Show all available commands")
async def commands_slash(interaction: discord.Interaction):
    embed = discord.Embed(title="Tred - Trivia & FunFacts Tracker", description="Track and share amazing trivia and funfacts!", color=0x10B981)
    embed.add_field(name="/random", value="Display a random trivia/funfact", inline=False)
    embed.add_field(name="/daily", value="Show today's trivia/funfact", inline=False)
    embed.add_field(name="/category <category>", value="Show all trivia from a specific category", inline=False)
    embed.add_field(name="/categories", value="List all available categories", inline=False)
    embed.add_field(name="/mine", value="Show all your contributed trivia", inline=False)
    embed.add_field(name="/create <text> <category>", value="Add a new trivia/funfact", inline=False)
    embed.add_field(name="/edit <id> <new_text>", value="Edit your trivia (or owner can edit any)", inline=False)
    embed.add_field(name="/delete <id>", value="Delete your trivia (or owner can delete any)", inline=False)
    embed.add_field(name="/search <keyword>", value="Search for trivia containing a keyword", inline=False)
    embed.add_field(name="/stats", value="Show trivia statistics", inline=False)
    
    owner_commands = "\n**Owner Commands:**\n"
    owner_commands += "`/all` - Show all trivia (owner only)\n"
    owner_commands += "`/cycle` - Cycle to next status trivia (owner only)\n"
    owner_commands += "`/rave` - Toggle RAVE MODE (owner only)\n"
    owner_commands += "`/shutdown` - Shutdown the bot (owner only)\n"
    owner_commands += "`/sync` - Force sync commands (owner only)"
    
    embed.add_field(name="Admin", value=owner_commands, inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="create", description="Create a new trivia/funfact")
async def create_slash(interaction: discord.Interaction, text: str, category: str):
    """
    Add a new trivia/funfact
    
    Parameters:
    - text: The trivia/funfact text
    - category: Category (e.g., Science, History, Nature, Technology, etc.)
    """
    trivia_list = load_trivia()
    
    contributor = interaction.user.name
    category_formatted = format_category_name(category)
    
    new_trivia = {
        "id": get_next_id(trivia_list),
        "text": text,
        "category": category_formatted,
        "contributor": contributor,
        "date": datetime.now().strftime("%d/%m/%Y")
    }
    
    trivia_list.append(new_trivia)
    save_trivia(trivia_list)
    
    await interaction.response.send_message(
        f'✅ Trivia #{new_trivia["id"]} added!\n"{text}"\nCategory: {category_formatted} | Contributor: {contributor}'
    )

@bot.tree.command(name="edit", description="Edit a trivia/funfact by ID")
async def edit_slash(interaction: discord.Interaction, trivia_id: int, new_text: str):
    """
    Edit an existing trivia/funfact
    
    Parameters:
    - trivia_id: The ID of the trivia to edit
    - new_text: The new text for the trivia
    """
    trivia_list = load_trivia()
    trivia = find_trivia_by_id(trivia_list, trivia_id)
    
    if not trivia:
        await interaction.response.send_message(f"Trivia #{trivia_id} not found.", ephemeral=True)
        return
    
    if not can_modify_trivia(interaction, trivia, OWNER_ID):
        await interaction.response.send_message(
            f"You can only edit your own trivia. This trivia was contributed by {trivia.get('contributor', 'Unknown')}.",
            ephemeral=True
        )
        return
    
    old_text = trivia["text"]
    trivia["text"] = new_text
    save_trivia(trivia_list)
    
    await interaction.response.send_message(
        f'✅ Trivia #{trivia_id} updated!\nOld: "{old_text}"\nNew: "{new_text}"'
    )

@bot.tree.command(name="delete", description="Delete a trivia/funfact by ID")
async def delete_slash(interaction: discord.Interaction, trivia_id: int):
    """
    Delete a trivia/funfact
    
    Parameters:
    - trivia_id: The ID of the trivia to delete
    """
    trivia_list = load_trivia()
    trivia = find_trivia_by_id(trivia_list, trivia_id)
    
    if not trivia:
        await interaction.response.send_message(f"Trivia #{trivia_id} not found.", ephemeral=True)
        return
    
    if not can_modify_trivia(interaction, trivia, OWNER_ID):
        await interaction.response.send_message(
            f"You can only delete your own trivia. This trivia was contributed by {trivia.get('contributor', 'Unknown')}.",
            ephemeral=True
        )
        return
    
    trivia_list.remove(trivia)
    save_trivia(trivia_list)
    
    await interaction.response.send_message(
        f'🗑️ Trivia #{trivia_id} deleted: "{trivia["text"]}"'
    )

@bot.tree.command(name="category", description="Show all trivia from a specific category")
async def category_slash(interaction: discord.Interaction, category: str):
    """
    View all trivia from a category
    
    Parameters:
    - category: The category to filter by
    """
    trivia_list = load_trivia()
    
    if not trivia_list:
        await interaction.response.send_message("No trivia yet.")
        return
    
    category_formatted = format_category_name(category)
    
    filtered = []
    for t in trivia_list:
        if t.get("category", "").lower() == category_formatted.lower():
            filtered.append(t)
    
    if not filtered:
        await interaction.response.send_message(f"No trivia found in category '{category_formatted}'.")
        return
    
    embed = discord.Embed(
        title=f"Trivia - {category_formatted}",
        description=f"Total: {len(filtered)} trivia item{'s' if len(filtered) != 1 else ''}",
        color=0x10B981
    )
    
    for t in filtered[:25]:  # Discord embed limit
        contributor = t.get("contributor", "Unknown")
        embed.add_field(
            name=f"#{t['id']} - {contributor}",
            value=f'{t["text"]} ({t["date"]})',
            inline=False
        )
    
    if len(filtered) > 25:
        embed.set_footer(text=f"Showing first 25 of {len(filtered)} results")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="categories", description="List all available categories")
async def categories_slash(interaction: discord.Interaction):
    trivia_list = load_trivia()
    
    if not trivia_list:
        await interaction.response.send_message("No trivia yet.")
        return
    
    categories = {}
    for t in trivia_list:
        cat = t.get("category", "Uncategorized")
        categories[cat] = categories.get(cat, 0) + 1
    
    sorted_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)
    
    embed = discord.Embed(
        title="Trivia Categories",
        description=f"Total categories: {len(sorted_categories)}",
        color=0x10B981
    )
    
    category_list = "\n".join([f"**{cat}**: {count} trivia" for cat, count in sorted_categories])
    embed.add_field(name="Available Categories", value=category_list, inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="search", description="Search for trivia containing a keyword")
async def search_slash(interaction: discord.Interaction, keyword: str):
    """
    Search trivia by keyword
    
    Parameters:
    - keyword: The keyword to search for
    """
    trivia_list = load_trivia()
    
    if not trivia_list:
        await interaction.response.send_message("No trivia yet.")
        return
    
    keyword_lower = keyword.lower()
    
    filtered = []
    for t in trivia_list:
        if keyword_lower in t["text"].lower():
            filtered.append(t)
    
    if not filtered:
        await interaction.response.send_message(f"No trivia found containing '{keyword}'.")
        return
    
    embed = discord.Embed(
        title=f"Search Results for '{keyword}'",
        description=f"Found: {len(filtered)} trivia item{'s' if len(filtered) != 1 else ''}",
        color=0x10B981
    )
    
    for t in filtered[:25]:  # Discord embed limit
        contributor = t.get("contributor", "Unknown")
        category = t.get("category", "General")
        embed.add_field(
            name=f"#{t['id']} - {category}",
            value=f'{t["text"]}\nContributor: {contributor} ({t["date"]})',
            inline=False
        )
    
    if len(filtered) > 25:
        embed.set_footer(text=f"Showing first 25 of {len(filtered)} results")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="stats", description="Show trivia statistics")
async def stats_slash(interaction: discord.Interaction):
    trivia_list = load_trivia()
    
    if not trivia_list:
        await interaction.response.send_message("No trivia yet.")
        return
    
    # Count by contributor
    contributors = {}
    for t in trivia_list:
        contrib = t.get("contributor", "Unknown")
        contributors[contrib] = contributors.get(contrib, 0) + 1
    
    # Count by category
    categories = {}
    for t in trivia_list:
        cat = t.get("category", "Uncategorized")
        categories[cat] = categories.get(cat, 0) + 1
    
    top_contributors = sorted(contributors.items(), key=lambda x: x[1], reverse=True)[:5]
    top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]
    
    embed = discord.Embed(
        title="📊 Trivia Statistics",
        description=f"Total trivia items: {len(trivia_list)}",
        color=0x10B981
    )
    
    contrib_text = "\n".join([f"**{name}**: {count} ({categorize_contributor(count)})" for name, count in top_contributors])
    embed.add_field(name="Top Contributors", value=contrib_text, inline=False)
    
    cat_text = "\n".join([f"**{cat}**: {count}" for cat, count in top_categories])
    embed.add_field(name="Top Categories", value=cat_text, inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="cycle", description="Cycle to next status trivia (owner only)")
async def cycle_slash(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("Owner-only command.", ephemeral=True)
        return
    
    trivia_list = load_trivia()
    
    if not trivia_list:
        await interaction.response.send_message("No trivia available.", ephemeral=True)
        return
    
    valid_trivia = get_valid_status_trivia(trivia_list)
    
    if not valid_trivia:
        await interaction.response.send_message("No trivia short enough for status.", ephemeral=True)
        return
    
    # Find current status trivia
    current_status = None
    if bot.activity:
        current_status = bot.activity.name
    
    current_index = 0
    
    if current_status:
        for i, t in enumerate(valid_trivia):
            cleaned_text = clean_trivia_text(t["text"])
            status_text = f'Did you know? {cleaned_text}'
            if status_text == current_status:
                current_index = i
                break
    
    # Get next trivia (wrap around)
    next_index = (current_index + 1) % len(valid_trivia)
    next_trivia = valid_trivia[next_index]
    
    await set_status_to_trivia(next_trivia)
    
    cleaned_text = clean_trivia_text(next_trivia["text"])
    await interaction.response.send_message(
        f'Status cycled to trivia #{next_trivia["id"]}:\nDid you know? {cleaned_text}'
    )

@bot.tree.command(name="rave", description="🎉 Toggle RAVE MODE - trivia cycles every 5 seconds!")
async def rave_slash(interaction: discord.Interaction, annoy: str = None):
    """
    Toggle rave mode - cycles trivia every 5 seconds!
    
    Parameters:
    - annoy: Optional - user ID (1234567890) or "everyone" to ping @everyone
    """
    global rave_mode_active, rave_task, annoy_user_id
    
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("Owner-only command.", ephemeral=True)
        return
    
    trivia_list = load_trivia()
    if not trivia_list:
        await interaction.response.send_message("No trivia available for rave mode!", ephemeral=True)
        return
    
    if rave_mode_active:
        # Stop rave mode
        rave_mode_active = False
        annoy_user_id = None
        
        if rave_task:
            rave_task.cancel()
            rave_task = None
        
        # Set back to daily trivia
        valid_trivia = get_valid_status_trivia(trivia_list)
        if valid_trivia:
            index = get_daily_trivia_index(valid_trivia)
            await set_status_to_trivia(valid_trivia[index])
        
        await interaction.response.send_message("🛑 Rave mode DISABLED. Back to chill vibes.")
    
    else:
        # Start rave mode
        rave_mode_active = True
        
        # Parse annoy parameter
        if annoy:
            annoy_lower = annoy.strip().lower()
            if annoy_lower == "everyone":
                annoy_user_id = "everyone"
            else:
                try:
                    annoy_user_id = int(annoy.strip())
                except ValueError:
                    await interaction.response.send_message("Invalid format. Use user ID (1234567890) or 'everyone'", ephemeral=True)
                    rave_mode_active = False
                    return
        else:
            annoy_user_id = None
        
        # Determine channel to spam
        spam_channel = interaction.channel if interaction.guild else None
        
        # Start the rave loop
        rave_task = asyncio.create_task(rave_mode_loop(spam_channel))
        
        if spam_channel:
            annoy_msg = ""
            if annoy_user_id == "everyone":
                annoy_msg = " | Pinging @everyone"
            elif annoy_user_id:
                annoy_msg = f" | Pinging <@{annoy_user_id}>"
            await interaction.response.send_message(f"🎉 RAVE MODE ACTIVATED! 🎉\nTrivia cycling every 5 seconds in this channel!{annoy_msg}")
        else:
            await interaction.response.send_message("🎉 RAVE MODE ACTIVATED! 🎉\nStatus cycling every 5 seconds (DM mode - no messages)")


@bot.tree.command(name="all", description="Show all trivia (owner only)")
async def all_slash(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("Owner-only command.", ephemeral=True)
        return
    
    trivia_list = load_trivia()
    
    if not trivia_list:
        await interaction.response.send_message("No trivia to display.")
        return
    
    embeds = []
    current_embed = discord.Embed(title="All Trivia", color=0x10B981)
    field_count = 0
    
    for t in trivia_list:
        if field_count >= 25:
            embeds.append(current_embed)
            current_embed = discord.Embed(title="All Trivia (continued)", color=0x10B981)
            field_count = 0
        
        contributor = t.get("contributor", "Unknown")
        category = t.get("category", "General")
        current_embed.add_field(
            name=f"#{t['id']} - {category}",
            value=f'{t["text"]}\nContributor: {contributor} ({t["date"]})',
            inline=False
        )
        field_count += 1
    
    embeds.append(current_embed)
    
    await interaction.response.send_message(embed=embeds[0])
    for embed in embeds[1:]:
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="mine", description="Show all your contributed trivia")
async def mine_slash(interaction: discord.Interaction):
    trivia_list = load_trivia()
    
    if not trivia_list:
        await interaction.response.send_message("No trivia yet.")
        return
    
    user_name = interaction.user.name
    
    filtered = []
    for t in trivia_list:
        if t.get("contributor", "").lower() == user_name.lower():
            filtered.append(t)
    
    if not filtered:
        await interaction.response.send_message(f"You haven't contributed any trivia yet, {user_name}!")
        return
    
    category = categorize_contributor(len(filtered))
    
    embed = discord.Embed(
        title=f"Trivia by {user_name}",
        description=f"Total: {len(filtered)} trivia item{'s' if len(filtered) != 1 else ''} - {category}",
        color=0x10B981
    )
    
    for t in filtered:
        cat = t.get("category", "General")
        embed.add_field(
            name=f"#{t['id']} - {cat} ({t['date']})",
            value=t["text"],
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="random", description="Display a random trivia/funfact")
async def random_slash(interaction: discord.Interaction):
    trivia_list = load_trivia()
    
    if not trivia_list:
        await interaction.response.send_message("No trivia to display")
        return
    
    seed = f"{datetime.now().timestamp()}{interaction.user.id}"
    hash_obj = hashlib.md5(seed.encode())
    hash_int = int(hash_obj.hexdigest(), 16)
    index = hash_int % len(trivia_list)
    
    t = trivia_list[index]
    contributor = t.get("contributor", "Unknown")
    category = t.get("category", "General")
    
    await interaction.response.send_message(
        f'#{t["id"]} - **{category}**\nDid you know? {t["text"]}\nContributor: {contributor} ({t["date"]})'
    )

@bot.tree.command(name="daily", description="Show today's trivia/funfact")
async def daily_slash(interaction: discord.Interaction):
    trivia_list = load_trivia()
    
    if not trivia_list:
        await interaction.response.send_message("No trivia to display")
        return
    
    index = get_daily_trivia_index(trivia_list)
    t = trivia_list[index]
    contributor = t.get("contributor", "Unknown")
    category = t.get("category", "General")
    
    await interaction.response.send_message(
        f'**Daily Trivia**\n#{t["id"]} - {category}\nDid you know? {t["text"]}\nContributor: {contributor} ({t["date"]})'
    )

@bot.tree.command(name="shutdown", description="Shutdown the bot (owner only)")
async def shutdown_slash(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    
    await interaction.response.send_message("Shutting down...")
    await bot.close()

@bot.tree.command(name="sync", description="Force sync slash commands (owner only)")
async def sync_slash(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Sync globally
        synced = await bot.tree.sync()
        
        # Also sync to current guild for immediate effect
        if interaction.guild:
            guild_synced = await bot.tree.sync(guild=interaction.guild)
            await interaction.followup.send(
                f"✅ Synced {len(synced)} global commands\n"
                f"✅ Synced {len(guild_synced)} commands to this server\n"
                f"Commands should appear immediately!",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"✅ Synced {len(synced)} global commands",
                ephemeral=True
            )
    except Exception as e:
        await interaction.followup.send(f"❌ Sync failed: {e}", ephemeral=True)

# -------------------------------
# Run the bot
# -------------------------------
if __name__ == "__main__":
    bot.run(TOKEN)
