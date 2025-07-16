# utils.py
import discord
import re

def format_nickname(format_string: str, member: discord.Member) -> str:
    """
    Formats a nickname by first stripping any existing [TAG] from the
    member's current display name, then applying the new format.
    """
    # Get the member's current name as seen in the server
    base_display_name = member.display_name

    # Use regex to find and remove a pattern like "[ANYTHING] " at the start of the name.
    # ^        - Start of the string
    # \[       - A literal opening square bracket
    # [^\]]+   - One or more characters that are NOT a closing bracket
    # \]       - A literal closing square bracket
    # \s*      - Zero or more whitespace characters (to catch the space after the tag)
    # This turns "[XYZ] Some User" into "Some User".
    stripped_name = re.sub(r'^\[[^\]]+\]\s*', '', base_display_name).strip()

    # Now, apply the new format string.
    # We use the newly stripped name for the {display_name} placeholder.
    # The {username} placeholder still uses the member's original, unique username.
    formatted = format_string.replace("{username}", member.name)
    formatted = formatted.replace("{display_name}", stripped_name)

    # Truncate to Discord's 32-character limit and return.
    return formatted[:32]