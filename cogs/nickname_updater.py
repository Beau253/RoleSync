import discord
from discord.ext import commands
import database as db

class NicknameUpdater(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def format_nickname(self, format_string: str, member: discord.Member) -> str:
        display_name = member.display_name
        formatted = format_string.replace("{username}", member.name)
        formatted = formatted.replace("{display_name}", display_name)
        return formatted[:32]

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot or before.roles == after.roles:
            return

        before_roles_set = set(before.roles)
        after_roles_set = set(after.roles)

        # --- LOGIC FOR ADDED ROLES ---
        added_roles = after_roles_set - before_roles_set
        for role in added_roles:
            rule = await db.get_rule(after.guild.id, role.id)
            if rule:
                # Rule found, save current state and apply new nickname
                previous_nickname = before.nick # Save the nickname *before* the change
                await db.save_nickname_history(after.id, after.guild.id, role.id, previous_nickname)

                new_nickname = self.format_nickname(rule['nickname_format'], after)
                
                try:
                    await after.edit(nick=new_nickname)
                    print(f"Updated nickname for {after.name} in {after.guild.name} due to role '{role.name}'.")
                except discord.Forbidden:
                    print(f"Error: Could not change nickname for {after.name}. Check permissions in '{after.guild.name}'.")
                except Exception as e:
                    print(f"An unexpected error occurred while changing nickname for {after.name}: {e}")

        # --- LOGIC FOR REMOVED ROLES ---
        removed_roles = before_roles_set - after_roles_set
        for role in removed_roles:
            # Check if we have a history for this role removal
            history = await db.get_nickname_history(after.id, after.guild.id, role.id)
            if history:
                # History found, revert the nickname and clean up the record
                previous_nickname = history['previous_nickname']

                try:
                    # Only revert if the name hasn't been changed by something else
                    # A simple check: if current nick is what the bot would have set, revert.
                    rule = await db.get_rule(after.guild.id, role.id)
                    if rule and after.nick == self.format_nickname(rule['nickname_format'], after):
                        await after.edit(nick=previous_nickname)
                        print(f"Reverted nickname for {after.name} in {after.guild.name} because role '{role.name}' was removed.")
                    elif not rule: # If rule was deleted, revert anyway if history exists
                         await after.edit(nick=previous_nickname)
                         print(f"Reverted nickname for {after.name} in {after.guild.name} because role '{role.name}' (rule deleted) was removed.")

                    # Clean up the history record regardless
                    await db.delete_nickname_history(after.id, after.guild.id, role.id)
                except discord.Forbidden:
                    print(f"Error: Could not revert nickname for {after.name}. Check permissions in '{after.guild.name}'.")
                except Exception as e:
                    print(f"An unexpected error occurred while reverting nickname for {after.name}: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(NicknameUpdater(bot))