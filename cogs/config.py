# cog/config.py

import discord
import logging
from discord import app_commands
from discord.ext import commands

# Import our database functions
import database as db

logger = logging.getLogger(__name__)

class Config(commands.Cog):
    """A cog for handling the bot's configuration commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Command Error Handler ---
    # This is a local error handler for this specific cog.
    # It will catch errors from the commands within this file.
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handles errors for commands in this cog."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You do not have the required permissions (Manage Nicknames) to use this command.",
                ephemeral=True
            )
        else:
            # For other errors, it's good practice to log them and inform the user.
            logger.info(f"An error occurred in a config command: {error}")
            await interaction.response.send_message(
                "An unexpected error occurred. Please try again later.",
                ephemeral=True
            )

    # --- Commands ---

    @app_commands.command(name="set-rule", description="Set or update a nickname rule for a specific role.")
    @app_commands.describe(
        role="The role that will trigger the nickname change.",
        format="The format for the new nickname. Use {username} or {display_name}."
    )
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def set_rule_command(self, interaction: discord.Interaction, role: discord.Role, format: str):
        """Command to set a nickname rule."""
        # Defer the response to give the bot time to process, especially the database call.
        await interaction.response.defer(ephemeral=True, thinking=True)

        # Basic validation for the format string
        if "{username}" not in format and "{display_name}" not in format:
            await interaction.followup.send(
                "The format string must include `{username}` or `{display_name}` as a placeholder."
            )
            return
        
        # Call the database function to save the rule
        await db.set_rule(interaction.guild.id, role.id, format)

        # Send a confirmation message
        await interaction.followup.send(
            f"✅ Rule successfully set for the **{role.name}** role.\n"
            f"New format: `{format}`"
        )


    @app_commands.command(name="remove-rule", description="Remove a nickname rule for a specific role.")
    @app_commands.describe(role="The role to remove the rule for.")
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def remove_rule_command(self, interaction: discord.Interaction, role: discord.Role):
        """Command to remove a nickname rule."""
        await interaction.response.defer(ephemeral=True, thinking=True)

        # Call the database function to delete the rule
        was_deleted = await db.remove_rule(interaction.guild.id, role.id)

        if was_deleted:
            await interaction.followup.send(f"✅ The rule for the **{role.name}** role has been removed.")
        else:
            await interaction.followup.send(f"ℹ️ No rule was found for the **{role.name}** role, so nothing was changed.")


    @app_commands.command(name="view-rules", description="View all active nickname rules for this server.")
    async def view_rules_command(self, interaction: discord.Interaction):
        """Command to view all configured rules for the server."""
        await interaction.response.defer(thinking=True)

        # Get all rules from the database for this guild
        all_rules = await db.get_all_rules(interaction.guild.id)

        if not all_rules:
            await interaction.followup.send("There are no nickname rules configured for this server.")
            return

        # Create a Discord Embed for a nice, clean display
        embed = discord.Embed(
            title=f"Nickname Rules for {interaction.guild.name}",
            color=discord.Color.blue()
        )
        
        description_lines = []
        for rule in all_rules:
            # Get the role object from the guild. It might have been deleted.
            role_obj = interaction.guild.get_role(int(rule['role_id']))
            role_mention = role_obj.mention if role_obj else f"`@deleted-role (ID: {rule['role_id']})`"
            
            description_lines.append(f"{role_mention} → `{rule['nickname_format']}`")

        embed.description = "\n".join(description_lines)
        embed.set_footer(text=f"Found {len(all_rules)} rule(s).")

        await interaction.followup.send(embed=embed)

    # In cogs/config.py, inside the Config class, after your other commands

    @app_commands.command(name="run-rule", description="Retroactively apply a nickname rule to all members.")
    @app_commands.describe(role="The role whose rule you want to apply to all members.")
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def run_rule_command(self, interaction: discord.Interaction, role: discord.Role):
        """Command to retroactively apply a rule."""
        # This can be a long process, so defer the response immediately.
        await interaction.response.defer(ephemeral=True, thinking=True)

        # 1. Check if a rule actually exists for this role.
        rule = await db.get_rule(interaction.guild.id, role.id)
        if not rule:
            await interaction.followup.send(
                f"❌ No rule found for the **{role.name}** role. Please set one with `/set-rule` first."
            )
            return

        nickname_format = rule['nickname_format']

        # 2. Initialize counters for the summary report.
        updated_count = 0
        skipped_count = 0
        failed_count = 0

        # 3. Fetch all members and iterate through them.
        # interaction.guild.fetch_members() is more robust for large servers.
        async for member in interaction.guild.fetch_members(limit=None):
            if member.bot:
                continue # Skip bots

            # Check if the member has the target role
            if role in member.roles:
                expected_nickname = self._format_nickname(nickname_format, member)

                # Check if an update is needed
                if member.nick != expected_nickname:
                    try:
                        # Before changing, save their current nick as history for the revert feature
                        await db.save_nickname_history(member.id, member.guild.id, role.id, member.nick)
                        await member.edit(nick=expected_nickname)
                        updated_count += 1
                    except discord.Forbidden:
                        # Bot lacks permissions to edit this member
                        failed_count += 1
                    except Exception as e:
                        failed_count += 1
                        logger.info(f"Failed to update {member.name} during run-rule: {e}")
                else:
                    # Nickname is already correct
                    skipped_count += 1

        # 4. Create and send the final summary report.
        embed = discord.Embed(
            title="Rule Execution Report",
            description=f"Finished applying the rule for the {role.mention} role.",
            color=discord.Color.green()
        )
        embed.add_field(name="✅ Members Updated", value=str(updated_count), inline=True)
        embed.add_field(name="ℹ️ Members Skipped", value=str(skipped_count), inline=True)
        embed.add_field(name="❌ Updates Failed", value=str(failed_count), inline=True)
        embed.set_footer(text="Failures are usually due to role hierarchy permissions.")

        await interaction.followup.send(embed=embed)

    # In cogs/config.py, inside the Config class

    async def _sync_all_guilds_history(self):
        """A reusable method to sync nickname history for all guilds."""
        logger.info("Starting baseline nickname history sync...")
        synced_guilds = 0
        for guild in self.bot.guilds:
            try:
                logger.info(f"Syncing history for guild: {guild.name} ({guild.id})")
                
                all_rules = await db.get_all_rules(guild.id)
                if not all_rules:
                    logger.info(f" -> No rules found for {guild.name}, skipping.")
                    continue

                rule_role_ids = {int(r['role_id']) for r in all_rules}

                member_count = 0
                history_entries_saved = 0
                async for member in guild.fetch_members(limit=None):
                    member_count += 1
                    if member.bot:
                        continue
                    
                    for role in member.roles:
                        if role.id in rule_role_ids:
                            await db.save_nickname_history(member.id, guild.id, role.id, member.nick)
                            history_entries_saved += 1
                
                logger.info(f" -> Scanned {member_count} members, saved/updated {history_entries_saved} history entries.")
                synced_guilds += 1

            except discord.Forbidden:
                logger.info(f" -> ERROR: Missing permissions to fetch members in {guild.name}. Skipping.")
            except Exception as e:
                logger.info(f" -> ERROR: An unexpected error during history sync for {guild.name}: {e}")

        logger.info(f"--- Baseline sync complete. Processed {synced_guilds}/{len(self.bot.guilds)} guilds. ---")

        # In cogs/config.py, inside the Config class

    @app_commands.command(name="sync-nicknames", description="Manually re-syncs the nickname history for all members.")
    @app_commands.checks.has_permissions(administrator=True) # Recommended for such a heavy command
    async def sync_nicknames_command(self, interaction: discord.Interaction):
        """Command to manually trigger the nickname history sync."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # Call our reusable sync method
        await self._sync_all_guilds_history()
        
        await interaction.followup.send("✅ Nickname history synchronization is complete.")

    @staticmethod
    def _format_nickname(format_string: str, member: discord.Member) -> str:
        """
        Helper to replace placeholders in the format string with member data.
        (This is a static copy of the helper in the other cog to avoid cross-imports)
        """
        display_name = member.display_name
        formatted = format_string.replace("{username}", member.name)
        formatted = formatted.replace("{display_name}", display_name)
        return formatted[:32] # Truncate to Discord's 32-character limit

# This special function is what discord.py looks for when it loads a cog.
async def setup(bot: commands.Bot):
    await bot.add_cog(Config(bot))