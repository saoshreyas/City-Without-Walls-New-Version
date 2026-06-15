"""
wsz6_play/engine/role_manager.py

Manages the mapping between player tokens and game roles for one session.

A *player token* is a UUID hex string issued to each connected player.
It is passed as a URL segment when the player opens the game WebSocket
(``/ws/game/<session_key>/<role_token>/``), allowing GameConsumer to
authenticate and look up the player's roles without relying on the
Django session cookie.
"""

import uuid
from typing import Dict, List, Optional


class PlayerInfo:
    """Mutable record for one connected player."""

    __slots__ = ('token', 'name', 'role_nums', 'is_bot', 'user_id', 'strategy')

    def __init__(
        self,
        token: str,
        name: str,
        is_bot: bool = False,
        user_id: Optional[int] = None,
        strategy: str = 'random',
    ):
        self.token    = token
        self.name     = name
        self.role_nums: List[int] = []   # empty = unassigned
        self.is_bot   = is_bot
        self.user_id  = user_id   # Django user ID, or None for guests
        self.strategy = strategy  # bot strategy: 'random' or 'first'

    @property
    def role_num(self) -> int:
        """Return first role or -1 (backward compat for bot / engine code)."""
        return self.role_nums[0] if self.role_nums else -1


class RoleManager:
    """Manages role assignments for one game session's lobby."""

    def __init__(self, roles_spec):
        """
        Args:
            roles_spec: an ``SZ_Roles_Spec`` instance from the PFF
                        (or the minimal default returned by
                        ``LobbyConsumer._default_roles_spec()``).
        """
        self.roles_spec = roles_spec
        self._players: Dict[str, PlayerInfo] = {}

    # ------------------------------------------------------------------
    # Player lifecycle
    # ------------------------------------------------------------------

    def add_player(self, name: str, user_id: Optional[int] = None) -> str:
        """Create a new player token, register the player as unassigned, and
        return the token."""
        token = uuid.uuid4().hex
        self._players[token] = PlayerInfo(token=token, name=name, user_id=user_id)
        return token

    def remove_player(self, token: str) -> None:
        self._players.pop(token, None)

    def get_player(self, token: str) -> Optional[PlayerInfo]:
        return self._players.get(token)

    # ------------------------------------------------------------------
    # Role assignment
    # ------------------------------------------------------------------

    def add_to_role(self, token: str, role_num: int) -> str:
        """Add a player to a role.

        Fails if the role is full (current count >= max_players) or the player
        is already in the role.  Returns '' on success, error string on failure.
        """
        player = self._players.get(token)
        if player is None:
            return "Unknown player token."
        roles = self.roles_spec.roles
        if not (0 <= role_num < len(roles)):
            return f"Role number {role_num} is out of range."
        if role_num in player.role_nums:
            return ""   # idempotent – already in role
        max_p = getattr(roles[role_num], 'max_players', 1)
        current_count = sum(1 for p in self._players.values() if role_num in p.role_nums)
        if current_count >= max_p:
            return f"Role '{roles[role_num].name}' is full ({current_count}/{max_p})."
        player.role_nums.append(role_num)
        return ""

    def remove_from_role(self, token: str, role_num: int) -> str:
        """Remove a player from a single role (keeps them in any other roles).

        If the player is a bot and has no remaining roles, removes them from
        the session entirely.  Returns '' on success, error string on failure.
        """
        player = self._players.get(token)
        if player is None:
            return "Unknown player token."
        if role_num not in player.role_nums:
            return ""   # idempotent
        player.role_nums.remove(role_num)
        if player.is_bot and not player.role_nums:
            del self._players[token]   # bots with no roles are removed entirely
        return ""

    def assign_role(self, token: str, role_num: int) -> str:
        """Backward-compat shim — delegates to add_to_role."""
        return self.add_to_role(token, role_num)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_roles_for_token(self, token: str) -> List[int]:
        """Return list of role_nums for a token."""
        p = self._players.get(token)
        return list(p.role_nums) if p else []

    def get_role_for_token(self, token: str) -> int:
        """Return first role_num for a token, or -1 if unassigned / unknown."""
        p = self._players.get(token)
        return p.role_num if p else -1

    def get_tokens_for_role(self, role_num: int) -> List[str]:
        """Return tokens of all players currently in role_num."""
        return [p.token for p in self._players.values() if role_num in p.role_nums]

    def get_token_for_role(self, role_num: int) -> Optional[str]:
        """Return the first token of a player in role_num, or None.

        Kept for backward compatibility; prefer get_tokens_for_role().
        """
        tokens = self.get_tokens_for_role(role_num)
        return tokens[0] if tokens else None

    def get_role_player_count(self, role_num: int) -> int:
        return sum(1 for p in self._players.values() if role_num in p.role_nums)

    def get_role_max_players(self, role_num: int) -> int:
        roles = self.roles_spec.roles
        if 0 <= role_num < len(roles):
            return getattr(roles[role_num], 'max_players', 1)
        return 1

    def can_join_role(self, role_num: int) -> bool:
        return self.get_role_player_count(role_num) < self.get_role_max_players(role_num)

    def player_has_role(self, token: str, role_num: int) -> bool:
        p = self._players.get(token)
        return p is not None and role_num in p.role_nums

    def get_all_players(self) -> List[PlayerInfo]:
        return list(self._players.values())

    def get_assigned_players(self) -> List[PlayerInfo]:
        return [p for p in self._players.values() if p.role_nums]

    def is_observer_role(self, role_num: int) -> bool:
        roles = self.roles_spec.roles
        if 0 <= role_num < len(roles):
            return roles[role_num].name.lower() == 'observer'
        return False

    def count_non_observer_filled(self) -> int:
        """Return the number of distinct non-observer roles that have a player."""
        filled_roles = {
            rn
            for p in self._players.values()
            for rn in p.role_nums
            if not self.is_observer_role(rn)
        }
        return len(filled_roles)

    def validate_for_start(self) -> str:
        """Return an error string if the game cannot start yet, or ``''``."""
        min_needed = getattr(self.roles_spec, 'min_players_to_start', 1)
        filled = self.count_non_observer_filled()
        if filled < min_needed:
            return (
                f"Need at least {min_needed} non-observer role(s) filled "
                f"(currently {filled})."
            )
        return ""

    def to_dict(self) -> dict:
        """Serialise for sending over WebSocket."""
        roles = self.roles_spec.roles
        return {
            'roles': [
                {
                    'role_num':      i,
                    'name':          r.name,
                    'description':   r.description,
                    'is_observer':   self.is_observer_role(i),
                    'max_players':   getattr(r, 'max_players', 1),
                    'current_count': self.get_role_player_count(i),
                    'players': [
                        {'token': p.token, 'name': p.name, 'is_bot': p.is_bot}
                        for p in self._players.values()
                        if i in p.role_nums
                    ],
                }
                for i, r in enumerate(roles)
            ],
            'unassigned': [
                {'token': p.token, 'name': p.name}
                for p in self._players.values()
                if not p.role_nums and not p.is_bot
            ],
        }
