import random

from client import Player

import json
import util


class Players:
    """
    Wrapper for an id->Player map

    Used to lookup players either by id (cheap) or by login (expensive, don't do this).
    
    Also responsible for general player logic, e.g remembering friendliness and colors of players.
    """
    def __init__(self, me):
        self.me = me
        "Logged in player. Can be None if we're not connected."
        self.coloredNicknames = False

        # UID -> Player map
        self._players = {}
        # Login -> Player map
        self._logins = {}

        # ids of the client's friends
        self.friends = set()

        # ids of the client's foes
        self.foes = set()

        # names of the client's clanmates
        self.clanlist = set()

    # Color table used by the following method
    # CAVEAT: This will break if the theme is loaded after the client package is imported
    colors = json.loads(util.readfile("client/colors.json"))
    randomcolors = json.loads(util.readfile("client/randomcolors.json"))

    def is_friend(self, user_id):
        """
        Convenience function for other modules to inquire about a user's friendliness.
        """
        return user_id in self.friends

    def is_foe(self, user_id):
        """
        Convenience function for other modules to inquire about a user's foeliness.
        """
        return user_id in self.foes

    def is_player(self, name):
        """
        Convenience function for other modules to inquire about a user's civilian status.
        """
        return name in self

    def get_user_color(self, user_id):
        """
        Returns a user's color depending on their status with relation to the FAF client
        """
        # Return default color if we're not logged in
        if self.me is None:
            return self.get_color("default")

        if user_id == self.me.id:
            return self.get_color("self")
        if user_id in self.friends:
            return self.get_color("friend")
        if user_id in self.foes:
            return self.get_color("foe")
        if user_id in self.clanlist:
            return self.get_color("clan")
        if self.coloredNicknames:
            return self.get_random_color(user_id)
        if user_id in self:
            return self.get_color("player")

        return self.get_color("default")

    def get_random_color(self, user_id):
        """Generate a random color from a name"""
        random.seed(user_id)
        return random.choice(self.randomcolors)

    def get_color(self, name):
        if name in self.colors:
            return self.colors[name]
        else:
            return self.colors["default"]

    def keys(self):
        return self._players.keys()

    def values(self):
        return self._players.values()

    def items(self):
        return self._players.items()

    def get(self, item, default):
        val = self.__getitem__(item)
        return val if val else default

    def get_id(self, name):
        if name in self._logins:
            return self._logins[name].id
        return -1

    def __contains__(self, item):
        return self.__getitem__(item) is not None

    def __getitem__(self, item):
        if isinstance(item, Player):
            return item
        if isinstance(item, int) and item in self._players:
            return self._players[item]
        if item in self._logins:
                return self._logins[item]

    def __setitem__(self, key, value):
        assert isinstance(key, int)
        self._players[key] = value
        self._logins[value.login] = value
