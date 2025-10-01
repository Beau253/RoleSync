# file: cogs/delegation.py

import discord
from discord import app_commands
from discord.ext import commands
from typing import List, Optional
import database as db
import logging

# --- Interactive View for Role Conflicts ---
class RoleConflictView(discord.ui.View):
    def __init__(self, target_user: discord.Member, roles_to_add: List[discord.Role], roles_to_remove: List[discord.Role]):
        super().__init__(timeout=180)  # 3 minute timeout
        self.target_user = target_user
        self.roles_to_add = roles_to_add
        self.roles_to_remove = roles_to_remove
        self.interaction: Optional[discord.Interaction] = None

    async def on_timeout(self) -> None:
        if self.interaction:
            for item in self.children:
                item.disabled = True
            await self.interaction.edit_original_response(content="⌛ Timed out. No action was taken.", view=self)

    @discord.ui.button(label="Confirm Transfer", style=discord.ButtonStyle.primary, custom_id="swap_roles")
    async def swap_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            # Perform all actions: remove old, add new
            await self.target_user.remove_roles(*self.roles_to_remove, reason=f"Hierarchy transfer by {interaction.user}")
            await self.target_user.add_roles(*self.roles_to_add, reason=f"Hierarchy transfer by {interaction.user}")
            
            add_mentions = ", ".join(r.mention for r in self.roles_to_add)
            remove_mentions = ", ".join(r.mention for r in self.roles_to_remove)
            await interaction.edit_original_response(content=f"✅ **Transfer Complete!**\n**Added:** {add_mentions}\n**Removed:** {remove_mentions}", view=None)
        except discord.Forbidden:
            await interaction.edit_original_response(content="❌ **Action Failed!** The bot's role is not high enough to manage these roles.", view=None)
        self.stop()

    @discord.ui.button(label="Add Only (No Removals)", style=discord.ButtonStyle.secondary, custom_id="add_only")
    async def add_only(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            await self.target_user.add_roles(*self.roles_to_add, reason=f"Granted by {interaction.user}")

            add_mentions = ", ".join(r.mention for r in self.roles_to_add)
            await interaction.edit_original_response(content=f"✅ **Action Complete!**\n**Added:** {add_mentions}\nUser now has both sets of roles.", view=None)
        except discord.Forbidden:
            await interaction.edit_original_response(content="❌ **Action Failed!** The bot's role is not high enough to assign these roles.", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Action cancelled. No roles were changed.", view=None)
        self.stop()

# --- Main Cog Class ---
class Delegation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Autocomplete Function ---
    async def manageable_roles_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        # If the user is an administrator, show all roles in the server.
        if interaction.user.guild_permissions.administrator:
            all_roles = interaction.guild.roles
            choices = [
                app_commands.Choice(name=role.name, value=str(role.id))
                for role in all_roles
                if current.lower() in role.name.lower() and not role.is_default() # Exclude @everyone
            ]
            return sorted(choices, key=lambda c: c.name)[:25]
        else:
            # For non-admins, show only their explicitly manageable roles.
            user_role_ids = [role.id for role in interaction.user.roles]
            manageable_role_ids = await db.get_manageable_roles_for_user(interaction.guild.id, user_role_ids)
            if not manageable_role_ids: return []
            
            choices = []
            for role_id in manageable_role_ids:
                role = interaction.guild.get_role(role_id)
                if role and current.lower() in role.name.lower():
                    choices.append(app_commands.Choice(name=role.name, value=str(role.id)))
            return choices[:25]

    # --- User-Facing Commands ---
    @app_commands.command(name="grant-role", description="Assign a role (and its dependencies) you have permission to manage.")
    @app_commands.describe(role="The main role you want to assign.", user="The member to grant the role to.")
    @app_commands.autocomplete(role=manageable_roles_autocomplete)
    async def grant_role(self, interaction: discord.Interaction, role: str, user: discord.Member):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        # --- 1. VERIFICATION ---
        role_id = int(role)
        target_role = interaction.guild.get_role(role_id)
        
        # Allow administrators to manage any role, otherwise check for delegated permissions.
        if not interaction.user.guild_permissions.administrator:
            user_role_ids = [r.id for r in interaction.user.roles]
            manageable_role_ids = await db.get_manageable_roles_for_user(interaction.guild.id, user_role_ids)
            if not target_role or role_id not in manageable_role_ids:
                return await interaction.followup.send("❌ You do not have permission to manage this role.")
        elif not target_role: # For admins, just make sure the role exists
            return await interaction.followup.send("❌ That role could not be found. It may have been deleted.")

        # --- 2. CALCULATE ROLES TO ADD (DEPENDENCY HIERARCHY) ---
        # Get all roles this role depends on (upward traversal).
        dependency_ids = await db.get_role_dependencies(interaction.guild.id, target_role.id)
        # Always include the target role itself in the list of roles to add.
        all_ids_to_add = set(dependency_ids) | {target_role.id}

        user_current_role_ids = {r.id for r in user.roles}
        final_add_ids = [rid for rid in all_ids_to_add if rid not in user_current_role_ids]
        roles_to_add = [interaction.guild.get_role(rid) for rid in final_add_ids if interaction.guild.get_role(rid)]

        if not roles_to_add:
            return await interaction.followup.send(f"🔷 {user.mention} already has the {target_role.mention} role and all its dependencies.")

        # --- 3. CALCULATE ROLES TO REMOVE (CONFLICT HIERARCHY) ---
        roles_to_remove = []
        conflicting_role_found = None
        # Find the first conflict to identify the conflicting hierarchy
        for r_add in roles_to_add:
            conflicting_role_found = await db.get_conflicting_role(interaction.guild.id, user.roles, r_add.id)
            if conflicting_role_found:
                break 

        if conflicting_role_found:
            # THE KEY CHANGE: Get the entire hierarchy of the conflicting role
            conflicting_hierarchy_ids = await db.get_full_hierarchy_for_role(interaction.guild.id, conflicting_role_found.id)
            # Find which of those roles the user actually has
            roles_to_remove = [r for r in user.roles if r.id in conflicting_hierarchy_ids]

        # --- 4. EXECUTE ACTION OR PROMPT USER ---
        if roles_to_remove:
            # Create the interactive prompt
            add_mentions = ", ".join(r.mention for r in roles_to_add)
            remove_mentions = ", ".join(r.mention for r in roles_to_remove)
            view = RoleConflictView(target_user=user, roles_to_add=roles_to_add, roles_to_remove=roles_to_remove)
            
            await interaction.followup.send(
                f"⚠️ **Hierarchy Conflict Detected!**\nThis action requires a transfer.\n\n**Roles to Add:** {add_mentions}\n**Roles to Remove:** {remove_mentions}\n\nPlease confirm how to proceed.",
                view=view
            )
            view.interaction = interaction
        else:
            # No conflict, just add the roles
            try:
                await user.add_roles(*roles_to_add, reason=f"Granted by {interaction.user} via delegation.")
                add_mentions = ", ".join(r.mention for r in roles_to_add)
                await interaction.followup.send(f"✅ Successfully granted: {add_mentions} to {user.mention}.")
            except discord.Forbidden:
                await interaction.followup.send("❌ **Action Failed!** The bot's role is not high enough to assign these roles.")
            except Exception as e:
                logging.error(f"Error in grant-role (no conflict): {e}")
                await interaction.followup.send("An unexpected error occurred.")

    @app_commands.command(name="revoke-role", description="Remove a role you have permission to manage.")
    @app_commands.describe(role="The role you want to remove.", user="The member to revoke the role from.")
    @app_commands.autocomplete(role=manageable_roles_autocomplete)
    async def revoke_role(self, interaction: discord.Interaction, role: str, user: discord.Member):
        await interaction.response.defer(ephemeral=True, thinking=True)
        role_id = int(role)
        target_role = interaction.guild.get_role(role_id)

        # Allow administrators to manage any role, otherwise check for delegated permissions.
        if not interaction.user.guild_permissions.administrator:
            user_role_ids = [r.id for r in interaction.user.roles]
            manageable_role_ids = await db.get_manageable_roles_for_user(interaction.guild.id, user_role_ids)
            if not target_role or role_id not in manageable_role_ids:
                return await interaction.followup.send("❌ You do not have permission to manage this role.")
        elif not target_role: # For admins, just make sure the role exists
            return await interaction.followup.send("❌ That role could not be found. It may have been deleted.")
        
        if target_role not in user.roles:
            return await interaction.followup.send(f"🔷 {user.mention} does not have the {target_role.mention} role.")
            
        try:
            await user.remove_roles(target_role, reason=f"Role revoked by {interaction.user} via delegation.")
            await interaction.followup.send(f"🗑️ Successfully revoked {target_role.mention} from {user.mention}.")
        except discord.Forbidden:
            await interaction.followup.send("❌ **Action Failed!** The bot's role is not high enough to remove this role.")
        except Exception as e:
            logging.error(f"Error in revoke-role: {e}")
            await interaction.followup.send("An unexpected error occurred.")


    # --- Admin Command Groups ---
    delegation_group = app_commands.Group(name="delegation", description="Commands to manage role delegation permissions.")
    exclusive_group = app_commands.Group(name="exclusive-group", description="Commands to manage mutually exclusive role groups.")
    dependency_group = app_commands.Group(name="dependency", description="Commands to manage role dependencies (hierarchies).")

    # --- Delegation Admin Commands ---
    @delegation_group.command(name="grant", description="Allow a manager role to manage another role.")
    @app_commands.checks.has_permissions(administrator=True)
    async def delegation_grant(self, interaction: discord.Interaction, manager_role: discord.Role, managed_role: discord.Role):
        await db.add_delegated_permission(interaction.guild.id, manager_role.id, managed_role.id)
        await interaction.response.send_message(f"✅ Success! Users with {manager_role.mention} can now manage {managed_role.mention}.", ephemeral=True)

    @delegation_group.command(name="revoke", description="Revoke a delegated role permission.")
    @app_commands.checks.has_permissions(administrator=True)
    async def delegation_revoke(self, interaction: discord.Interaction, manager_role: discord.Role, managed_role: discord.Role):
        await db.remove_delegated_permission(interaction.guild.id, manager_role.id, managed_role.id)
        await interaction.response.send_message(f"🗑️ Permission revoked. Users with {manager_role.mention} can no longer manage {managed_role.mention}.", ephemeral=True)

    @delegation_group.command(name="list", description="List all current role delegation permissions.")
    @app_commands.checks.has_permissions(administrator=True)
    async def delegation_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        permissions = await db.get_all_delegated_permissions(interaction.guild.id)
        if not permissions:
            return await interaction.followup.send("No role delegation permissions are configured.")

        embed = discord.Embed(title="Delegated Role Permissions", color=discord.Color.blue())
        description = ""
        for perm in permissions:
            manager = interaction.guild.get_role(perm['manager_role_id'])
            managed = interaction.guild.get_role(perm['managed_role_id'])
            if manager and managed:
                description += f"{manager.mention} can manage {managed.mention}\n"
        embed.description = description
        await interaction.followup.send(embed=embed)


    # --- Exclusivity Admin Commands ---
    @exclusive_group.command(name="add", description="Add a role to a mutually exclusive group.")
    @app_commands.checks.has_permissions(administrator=True)
    async def exclusive_add(self, interaction: discord.Interaction, group_name: str, role: discord.Role):
        await db.add_role_to_exclusive_group(interaction.guild.id, group_name, role.id)
        await interaction.response.send_message(f"✅ Added {role.mention} to the **{group_name.lower()}** exclusive group.", ephemeral=True)

    @exclusive_group.command(name="remove", description="Remove a role from its exclusive group.")
    @app_commands.checks.has_permissions(administrator=True)
    async def exclusive_remove(self, interaction: discord.Interaction, role: discord.Role):
        await db.remove_role_from_exclusive_group(interaction.guild.id, role.id)
        await interaction.response.send_message(f"🗑️ Removed {role.mention} from its exclusive group.", ephemeral=True)

    @exclusive_group.command(name="list", description="List all mutually exclusive role groups.")
    @app_commands.checks.has_permissions(administrator=True)
    async def exclusive_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        groups_raw = await db.get_all_exclusive_groups(interaction.guild.id)
        if not groups_raw:
            return await interaction.followup.send("No mutually exclusive role groups are configured.")
        
        groups = {}
        for item in groups_raw:
            if item['group_name'] not in groups:
                groups[item['group_name']] = []
            groups[item['group_name']].append(item['role_id'])

        embed = discord.Embed(title="Mutually Exclusive Role Groups", color=discord.Color.orange())
        for name, role_ids in groups.items():
            role_mentions = [interaction.guild.get_role(rid).mention for rid in role_ids if interaction.guild.get_role(rid)]
            embed.add_field(name=f"Group: `{name}`", value=", ".join(role_mentions) or "No valid roles.", inline=False)
        await interaction.followup.send(embed=embed)


    # --- Dependency Admin Commands ---
    @dependency_group.command(name="add", description="Set a dependency where one role requires another.")
    @app_commands.checks.has_permissions(administrator=True)
    async def dependency_add(self, interaction: discord.Interaction, role: discord.Role, requires: discord.Role):
        await db.add_dependency(interaction.guild.id, role.id, requires.id)
        await interaction.response.send_message(f"✅ Dependency set: {role.mention} now requires {requires.mention}.", ephemeral=True)

    @dependency_group.command(name="remove", description="Remove a role dependency.")
    @app_commands.checks.has_permissions(administrator=True)
    async def dependency_remove(self, interaction: discord.Interaction, role: discord.Role, requires: discord.Role):
        await db.remove_dependency(interaction.guild.id, role.id, requires.id)
        await interaction.response.send_message(f"🗑️ Dependency removed: {role.mention} no longer requires {requires.mention}.", ephemeral=True)
        
    @dependency_group.command(name="list", description="List all configured role dependencies.")
    @app_commands.checks.has_permissions(administrator=True)
    async def dependency_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        dependencies = await db.get_all_dependencies(interaction.guild.id)
        if not dependencies:
            return await interaction.followup.send("No role dependencies are configured.")

        embed = discord.Embed(title="Role Dependencies", color=discord.Color.purple())
        description = ""
        for dep in dependencies:
            role = interaction.guild.get_role(dep['role_id'])
            requires = interaction.guild.get_role(dep['required_role_id'])
            if role and requires:
                description += f"{role.mention} requires {requires.mention}\n"
        embed.description = description
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Delegation(bot))