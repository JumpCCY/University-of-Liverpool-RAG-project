import json

with open("liverpool_guilds.json", "r") as f:
    data = json.load(f)

    guilds = []
    for guild in data:
        listing = {}
        name = guild.get("guild_name", "No name available")
        long_desc = guild.get("long_description", "No long description available")
        listing["description"] = long_desc
        listing["length"] = len(long_desc)
        guilds.append(listing)

    for guild in guilds:
        description = guild["description"]
        words = description.split(" ")
        guild["word_count"] = len(words)

    print(max(guilds, key=lambda x: x["word_count"]))