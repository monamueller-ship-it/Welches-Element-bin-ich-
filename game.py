from __future__ import annotations
import random, secrets, time, json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).parent / 'elements.json'
ELEMENTS = json.loads(DATA_PATH.read_text(encoding='utf-8'))
CARD_BY_ID = {e['id']: e for e in ELEMENTS}
# 24 Hauptgruppen-Elemente; board order is randomized per room.
BOARD_POOL = [
    'h','he','li','be','b','c','n','o','f','ne','na','mg','al','si','p','s','cl','ar','k','ca','ga','ge','as','se'
]

class GameError(ValueError): pass

def public_card(e: dict[str, Any]) -> dict[str, Any]:
    return {'id': e['id'], 'symbol': e['symbol'], 'name': e['name'], 'atomicNumber': e['atomicNumber']}

@dataclass
class Player:
    id: str
    token: str
    name: str
    is_host: bool = False
    connected: bool = False

@dataclass
class GameRoom:
    code: str
    players: dict[str, Player] = field(default_factory=dict)
    phase: str = 'lobby'
    board: list[str] = field(default_factory=list)
    secrets: dict[str, str] = field(default_factory=dict)
    eliminated: dict[str, set[int]] = field(default_factory=dict)
    active_player_id: str | None = None
    winner_id: str | None = None
    turn_number: int = 0
    updated_at: float = field(default_factory=time.time)

    def touch(self): self.updated_at = time.time()

    @property
    def player_list(self): return list(self.players.values())

    def add_player(self, name: str) -> Player:
        if self.phase != 'lobby': raise GameError('Das Spiel läuft bereits.')
        if len(self.players) >= 2: raise GameError('Der Raum ist bereits voll.')
        name = ' '.join(name.strip().split())[:24]
        if not name: raise GameError('Bitte gib einen Namen ein.')
        if any(p.name.lower() == name.lower() for p in self.players.values()):
            raise GameError('Dieser Name wird bereits verwendet.')
        p = Player(secrets.token_urlsafe(9), secrets.token_urlsafe(18), name, is_host=not self.players)
        self.players[p.id] = p
        self.touch(); return p

    def authenticate(self, pid, token):
        p = self.players.get(pid)
        if not p or not secrets.compare_digest(p.token, token): raise GameError('Sitzung ungültig.')
        return p

    def mark_connected(self, pid, value):
        if pid in self.players: self.players[pid].connected = value; self.touch()

    def start(self, pid):
        p=self.authenticate(pid,'') if False else self.players.get(pid)
        if not p or not p.is_host: raise GameError('Nur der Gastgeber kann starten.')
        if len(self.players) != 2: raise GameError('Es müssen genau zwei Spieler beitreten.')
        rng=random.Random(secrets.randbits(64)); self.board=BOARD_POOL[:]; rng.shuffle(self.board)
        for player in self.players.values():
            self.secrets[player.id] = rng.choice(self.board)
        # distinct secret cards
        a,b=list(self.players)
        while self.secrets[a] == self.secrets[b]: self.secrets[b]=rng.choice(self.board)
        self.eliminated={pid:set() for pid in self.players}
        self.active_player_id=a; self.turn_number=1; self.phase='playing'; self.winner_id=None; self.touch()

    def eliminate(self, pid, index):
        if self.phase != 'playing': raise GameError('Das Spiel ist nicht aktiv.')
        if pid != self.active_player_id: raise GameError('Du bist gerade nicht am Zug.')
        if not isinstance(index,int) or index<0 or index>=len(self.board): raise GameError('Ungültige Karte.')
        if index in self.eliminated[pid]: raise GameError('Diese Karte ist bereits umgedreht.')
        if len(self.eliminated[pid]) >= 23: raise GameError('Eine Karte muss für den Tipp übrig bleiben.')
        self.eliminated[pid].add(index); self.touch()

    def end_turn(self, pid):
        if self.phase != 'playing' or pid != self.active_player_id: raise GameError('Du bist gerade nicht am Zug.')
        self.active_player_id=self._other(pid); self.turn_number+=1; self.touch()

    def guess(self, pid, index):
        if self.phase != 'playing' or pid != self.active_player_id: raise GameError('Du bist gerade nicht am Zug.')
        if index in self.eliminated[pid]: raise GameError('Diese Karte ist bereits umgedreht.')
        target=self.board[index]
        if target == self.secrets[self._other(pid)]:
            self.phase='finished'; self.winner_id=pid; self.touch(); return True
        # Wrong final guess: player loses the right to guess; opponent continues.
        self.eliminated[pid].add(index)
        self.active_player_id=self._other(pid); self.turn_number+=1; self.touch(); return False

    def _other(self,pid):
        ids=list(self.players)
        if pid not in ids: raise GameError('Spieler unbekannt.')
        return ids[1] if ids[0]==pid else ids[0]

    def reset(self,pid):
        p=self.players.get(pid)
        if not p or not p.is_host: raise GameError('Nur der Gastgeber kann neu starten.')
        self.phase='lobby'; self.board=[]; self.secrets={}; self.eliminated={}; self.active_player_id=None; self.winner_id=None; self.turn_number=0; self.touch()

    def public_state(self, viewer):
        vp=self.players[viewer]
        other=self._other(viewer) if len(self.players)==2 else None
        remaining=[i for i in range(24) if i not in self.eliminated.get(viewer,set())]
        active_name=self.players[self.active_player_id].name if self.active_player_id in self.players else ''
        return {
            'roomCode':self.code,'phase':self.phase,'turnNumber':self.turn_number,'activePlayerId':self.active_player_id,
            'winnerId':self.winner_id,'you':{'id':vp.id,'name':vp.name,'isHost':vp.is_host},
            'players':[{'id':p.id,'name':p.name,'isHost':p.is_host,'connected':p.connected} for p in self.players.values()],
            'board':[public_card(CARD_BY_ID[x]) for x in self.board],
            'secret': public_card(CARD_BY_ID[self.secrets[viewer]]) if viewer in self.secrets else None,
            'eliminated':sorted(self.eliminated.get(viewer,set())),
            'remainingCount':len(remaining),
            'opponentName':self.players[other].name if other else '',
            'status': self.status(viewer,active_name),
        }

    def status(self, viewer, active_name):
        if self.phase=='lobby': return 'Warte auf den zweiten Spieler.' if len(self.players)<2 else 'Bereit – der Gastgeber kann starten.'
        if self.phase=='playing': return 'Du bist am Zug.' if viewer==self.active_player_id else f'{active_name} ist am Zug.'
        if self.phase=='finished': return 'Du gewinnst!' if viewer==self.winner_id else f'{self.players[self.winner_id].name} gewinnt.'
        return ''
