from __future__ import annotations
import argparse
import copy
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from time import time
from typing import Tuple, TypeVar, Type, Iterable, ClassVar
import random
import requests
import validators


# maximum and minimum values for our heuristic scores (usually represents an end of game condition)
MAX_HEURISTIC_SCORE = 2000000000
MIN_HEURISTIC_SCORE = -2000000000

class UnitType(Enum):
    """Every unit type."""
    AI = 0
    Tech = 1
    Virus = 2
    Program = 3
    Firewall = 4

class Player(Enum):
    """The 2 players."""
    Attacker = 0
    Defender = 1

    def next(self) -> Player:
        """The next (other) player."""
        if self is Player.Attacker:
            return Player.Defender
        else:
            return Player.Attacker
        
class Direction(Enum):
    """Every direction a unit can move"""
    Up = 0
    Right = 1
    Down = 2
    Left = 3

class ActionType(Enum):
    """Every action a unit can take"""
    SelfDestruct = 0
    Move = 1
    Attack = 2
    Repair = 3

class GameType(Enum):
    AttackerVsDefender = 0
    AttackerVsComp = 1
    CompVsDefender = 2
    CompVsComp = 3

class GameTypeConverter:
    @staticmethod
    def convert_game_type(game_type):
        game_type_mapping = {
            GameType.AttackerVsDefender: "Player 1 = H, Player 2 = H",
            GameType.AttackerVsComp: "Player 1 = H, Player 2 = AI",
            GameType.CompVsDefender: "Player 1 = AI, Player 2 = H",
            GameType.CompVsComp: "Player 1 = AI, Player 2 = AI",
        }

        return game_type_mapping.get(game_type, "Unknown Game Type")

##############################################################################################################

@dataclass(slots=True)
class Unit:
    player: Player = Player.Attacker
    type: UnitType = UnitType.Program
    health : int = 9
    # class variable: damage table for units (based on the unit type constants in order)
    damage_table : ClassVar[list[list[int]]] = [
        [3,3,3,3,1], # AI
        [1,1,6,1,1], # Tech
        [9,6,1,6,1], # Virus
        [3,3,3,3,1], # Program
        [1,1,1,1,1], # Firewall
    ]
    # class variable: repair table for units (based on the unit type constants in order)
    repair_table : ClassVar[list[list[int]]] = [
        [0,1,1,0,0], # AI
        [3,0,0,3,3], # Tech
        [0,0,0,0,0], # Virus
        [0,0,0,0,0], # Program
        [0,0,0,0,0], # Firewall
    ]

    def is_alive(self) -> bool:
        """Are we alive ?"""
        return self.health > 0

    def mod_health(self, health_delta : int):
        """Modify this unit's health by delta amount."""
        self.health += health_delta
        if self.health < 0:
            self.health = 0
        elif self.health > 9:
            self.health = 9

    def has_full_health(self) -> bool:
        if self.health == 9:
            return True
        return False

    def to_string(self) -> str:
        """Text representation of this unit."""
        p = self.player.name.lower()[0]
        t = self.type.name.upper()[0]
        return f"{p}{t}{self.health}"
    
    def __str__(self) -> str:
        """Text representation of this unit."""
        return self.to_string()
    
    def damage_amount(self, target: Unit) -> int:
        """How much can this unit damage another unit."""
        amount = self.damage_table[self.type.value][target.type.value]
        if target.health - amount < 0:
            return target.health
        return amount

    def repair_amount(self, target: Unit) -> int:
        """How much can this unit repair another unit."""
        amount = self.repair_table[self.type.value][target.type.value]
        if target.health + amount > 9:
            return 9 - target.health
        return amount
    
    def is_valid_movement(self, player: Player, direction: Direction) -> bool:
        # Attacker units except Virus can move up or left. Virus moves in any direction
        if player == Player.Attacker:
            if self.type == UnitType.AI or self.type == UnitType.Program or self.type == UnitType.Firewall:
                if direction == Direction.Up or direction == Direction.Left:
                    return True
                return False

            if self.type == UnitType.Virus:
                return True
            
        # Defender units except Tech can move down or right. Tech moves in any direction
        if player == Player.Defender:
            if self.type == UnitType.AI or self.type == UnitType.Program or self.type == UnitType.Firewall:
                if direction == Direction.Down or direction == Direction.Right:
                    return True
                return False

            if self.type == UnitType.Tech:
                return True


##############################################################################################################

@dataclass(slots=True)
class Coord:
    """Representation of a game cell coordinate (row, col)."""
    row : int = 0
    col : int = 0

    def col_string(self) -> str:
        """Text representation of this Coord's column."""
        coord_char = '?'
        if self.col < 16:
                coord_char = "0123456789abcdef"[self.col]
        return str(coord_char)

    def row_string(self) -> str:
        """Text representation of this Coord's row."""
        coord_char = '?'
        if self.row < 26:
                coord_char = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[self.row]
        return str(coord_char)

    def to_string(self) -> str:
        """Text representation of this Coord."""
        return self.row_string()+self.col_string()
    
    def __str__(self) -> str:
        """Text representation of this Coord."""
        return self.to_string()
    
    def clone(self) -> Coord:
        """Clone a Coord."""
        return copy.copy(self)

    def iter_range(self, dist: int) -> Iterable[Coord]:
        """Iterates over Coords inside a rectangle centered on our Coord."""
        for row in range(self.row-dist,self.row+1+dist):
            for col in range(self.col-dist,self.col+1+dist):
                yield Coord(row,col)

    def iter_adjacent(self) -> Iterable[Coord]:
        """Iterates over adjacent Coords."""
        yield Coord(self.row-1,self.col)
        yield Coord(self.row,self.col-1)
        yield Coord(self.row+1,self.col)
        yield Coord(self.row,self.col+1)

    def equals(self, target: Coord) -> bool:
        if (self.row == target.row and self.col == target.col):
            return True
        return False

    @classmethod
    def from_string(cls, s : str) -> Coord | None:
        """Create a Coord from a string. ex: D2."""
        s = s.strip()
        for sep in " ,.:;-_":
                s = s.replace(sep, "")
        if (len(s) == 2):
            coord = Coord()
            coord.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coord.col = "0123456789abcdef".find(s[1:2].lower())
            return coord
        else:
            return None

##############################################################################################################

@dataclass(slots=True)
class CoordPair:
    """Representation of a game move or a rectangular area via 2 Coords."""
    src : Coord = field(default_factory=Coord)
    dst : Coord = field(default_factory=Coord)

    def to_string(self) -> str:
        """Text representation of a CoordPair."""
        return self.src.to_string()+" "+self.dst.to_string()
    
    def __str__(self) -> str:
        """Text representation of a CoordPair."""
        return self.to_string()

    def clone(self) -> CoordPair:
        """Clones a CoordPair."""
        return copy.copy(self)

    def iter_rectangle(self) -> Iterable[Coord]:
        """Iterates over cells of a rectangular area."""
        for row in range(self.src.row,self.dst.row+1):
            for col in range(self.src.col,self.dst.col+1):
                yield Coord(row,col)

    def is_adjacent(self) -> bool:
        for adj_coord in self.src.iter_adjacent():
            if adj_coord.col == self.dst.col and adj_coord.row == self.dst.row:
                return True
        
        return False
    
    def are_coords_equal(self) -> bool:
        if self.src.equals(self.dst):
            return True
        return False
    
    def get_direction(self) -> Direction:
        srcRow = self.src.row
        srcCol = self.src.col
        dstRow = self.dst.row
        dstCol = self.dst.col

        if srcRow < dstRow and srcCol == dstCol:
            return Direction.Down
        if srcRow > dstRow and srcCol == dstCol:
            return Direction.Up
        if srcRow == dstRow and srcCol < dstCol:
            return Direction.Right
        if srcRow == dstRow and srcCol > dstCol:
            return Direction.Left

    @classmethod
    def from_quad(cls, row0: int, col0: int, row1: int, col1: int) -> CoordPair:
        """Create a CoordPair from 4 integers."""
        return CoordPair(Coord(row0,col0),Coord(row1,col1))
    
    @classmethod
    def from_dim(cls, dim: int) -> CoordPair:
        """Create a CoordPair based on a dim-sized rectangle."""
        return CoordPair(Coord(0,0),Coord(dim-1,dim-1))
    
    @classmethod
    def from_string(cls, s : str) -> CoordPair | None:
        """Create a CoordPair from a string. ex: A3 B2"""
        s = s.strip()
        for sep in " ,.:;-_":
                s = s.replace(sep, "")
        if (len(s) == 4):
            coords = CoordPair()
            coords.src.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coords.src.col = "0123456789abcdef".find(s[1:2].lower())
            coords.dst.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[2:3].upper())
            coords.dst.col = "0123456789abcdef".find(s[3:4].lower())
            return coords
        else:
            return None

##############################################################################################################

@dataclass(slots=True)
class Options:
    """Representation of the game options."""
    dim: int = 5
    max_depth : int | None = 4
    min_depth : int | None = 2
    max_time : float | None = 5.0
    game_type : GameType = GameType.AttackerVsDefender
    alpha_beta : bool = True
    max_turns : int | None = 100
    randomize_moves : bool = True
    broker : str | None = None
    heuristic : str | None = None

##############################################################################################################

@dataclass(slots=True)
class Stats:
    """Representation of the global game statistics."""
    evaluations_per_depth : dict[int,int] = field(default_factory=dict)
    total_seconds: float = 0.0

##############################################################################################################

@dataclass(slots=True)
class Game:
    """Representation of the game state."""
    board: list[list[Unit | None]] = field(default_factory=list)
    next_player: Player = Player.Attacker
    turns_played : int = 0
    options: Options = field(default_factory=Options)
    stats: Stats = field(default_factory=Stats)
    _attacker_has_ai : bool = True
    _defender_has_ai : bool = True
    file_name : str = ""
    skip_logs : bool = False

    def __post_init__(self):
        """Automatically called after class init to set up the default board state."""
        dim = self.options.dim
        self.file_name = f"gameTrace-{str(self.options.alpha_beta).lower()}-{self.options.max_time}-{self.options.max_turns}.txt"
        self.board = [[None for _ in range(dim)] for _ in range(dim)]
        md = dim-1
        self.set(Coord(0,0),Unit(player=Player.Defender,type=UnitType.AI))
        self.set(Coord(1,0),Unit(player=Player.Defender,type=UnitType.Tech))
        self.set(Coord(0,1),Unit(player=Player.Defender,type=UnitType.Tech))
        self.set(Coord(2,0),Unit(player=Player.Defender,type=UnitType.Firewall))
        self.set(Coord(0,2),Unit(player=Player.Defender,type=UnitType.Firewall))
        self.set(Coord(1,1),Unit(player=Player.Defender,type=UnitType.Program))
        self.set(Coord(md,md),Unit(player=Player.Attacker,type=UnitType.AI))
        self.set(Coord(md-1,md),Unit(player=Player.Attacker,type=UnitType.Virus))
        self.set(Coord(md,md-1),Unit(player=Player.Attacker,type=UnitType.Virus))
        self.set(Coord(md-2,md),Unit(player=Player.Attacker,type=UnitType.Program))
        self.set(Coord(md,md-2),Unit(player=Player.Attacker,type=UnitType.Program))
        self.set(Coord(md-1,md-1),Unit(player=Player.Attacker,type=UnitType.Firewall))

    def dump_to_output_file(self, output_file_data: dict[str, str], append: bool = True):
        if (self.skip_logs):
            return
        mode = "a" if append else "w"
        with open(self.file_name, mode) as f:
            for key, value in output_file_data.items():
                f.write(f"{key}: {value}\n")
            f.write(f"{'=' * 60}\n")

    def clone(self) -> Game:
        """Make a new copy of a game for minimax recursion.

        Shallow copy of everything except the board (options and stats are shared).
        skip_logs is set to true to avoid generating or modifying log files
        """
        new = copy.copy(self)
        new.board = copy.deepcopy(self.board)
        new.skip_logs = True
        return new

    def is_empty(self, coord : Coord) -> bool:
        """Check if contents of a board cell of the game at Coord is empty (must be valid coord)."""
        return self.board[coord.row][coord.col] is None

    def get(self, coord : Coord) -> Unit | None:
        """Get contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            return self.board[coord.row][coord.col]
        else:
            return None

    def set(self, coord : Coord, unit : Unit | None):
        """Set contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            self.board[coord.row][coord.col] = unit

    def remove_dead(self, coord: Coord):
        """Remove unit at Coord if dead."""
        unit = self.get(coord)
        if unit is not None and not unit.is_alive():
            self.set(coord,None)
            if unit.type == UnitType.AI:
                if unit.player == Player.Attacker:
                    self._attacker_has_ai = False
                else:
                    self._defender_has_ai = False

    def mod_health(self, coord : Coord, health_delta : int):
        """Modify health of unit at Coord (positive or negative delta)."""
        target = self.get(coord)
        if target is not None:
            target.mod_health(health_delta)
            self.remove_dead(coord)

    def perform_self_distruct(self, src: Coord):
        """Iterate over surrounding squares and damage units therein, then delete selected unit"""
        # Damage surroundings
        for dst in src.iter_range(1):
            if src.equals(dst):
                continue
            self.mod_health(dst, -2)
        
        # Delete self
        src_unit = self.get(src)
        self.mod_health(src, -src_unit.health)

    def perform_fight(self, coords : CoordPair):
        """Combat is bidirectional and damage is dealt even if unit dies, so extract damage values first"""
        src_unit = self.get(coords.src)
        dst_unit = self.get(coords.dst)
        damage_to_dst = src_unit.damage_amount(dst_unit)
        damage_to_src = dst_unit.damage_amount(src_unit)

        self.mod_health(coords.src, -damage_to_src)
        self.mod_health(coords.dst, -damage_to_dst)

    def perform_repair(self, coords: CoordPair):
        """Repair value is retrieved from Unit class"""
        src_unit = self.get(coords.src)
        dst_unit = self.get(coords.dst)
        repair_to_dst = src_unit.repair_amount(dst_unit)

        self.mod_health(coords.dst, repair_to_dst)

    def is_repair_zero(self, src_unit: Unit, dst_unit: Unit) -> bool:
        return src_unit.repair_amount(dst_unit) <= 0

    # Unit is engaged in combat if there is at least 1 enemy unit adjacent
    def is_engaged_in_combat(self, src : Coord) -> bool:
        if self.next_player == Player.Attacker:
            enemy = Player.Defender
        else:
            enemy = Player.Attacker

        for adj in src.iter_adjacent():
            dst_unit = self.get(adj)
            if dst_unit is not None and dst_unit.player == enemy:
                return True
            
        return False
    
    # Check move validity based on player and unit type
    def is_movement_direction_valid(self, unit: Unit, coords: CoordPair) -> bool:
        movementDirection = coords.get_direction()
        return unit.is_valid_movement(self.next_player, movementDirection)

    def is_valid_move(self, coords : CoordPair) -> Tuple[bool, ActionType]:
        """Validate a move expressed as a CoordPair."""
        # Check if coords are in-bounds
        if not self.is_valid_coord(coords.src) or not self.is_valid_coord(coords.dst):
            return (False, None)
        
        # Check if src coord is player unit
        src_unit = self.get(coords.src)
        if src_unit is None or src_unit.player != self.next_player:
            return (False, None)
        
        # If dst is same as source, return true (this is the self destruct)
        if coords.are_coords_equal():
            return (True, ActionType.SelfDestruct)
        
        # src and dst are not the same. Check if dst coord is adjacent to src coord
        if not coords.is_adjacent():
            return (False, None)
        
        # We've checked spaces are not equal, adjacent, in-bounds, and player unit is chosen.
        # Now there's 3 possibilities: dst is empty, 
        # dst is occupied by friendly unit, or dst is occupied by enemy unit

        # If dst is empty space, check if no enemies are adjacent (unless unit is tech or virus), then check if movement is valid
        dst_unit = self.get(coords.dst)
        if (dst_unit is None):
            engaged = self.is_engaged_in_combat(coords.src)
            if engaged and src_unit.type is not UnitType.Tech and src_unit.type is not UnitType.Virus:
                return (False, None)
            if not self.is_movement_direction_valid(src_unit, coords):
                return (False, None)
            return (True, ActionType.Move)
    
        # If dst is friendly square, check if src unit is Tech (this is the repair)
        # then make sure target is not a virus or already at full health
        if dst_unit.player == self.next_player:
            if src_unit.type == UnitType.Tech or src_unit.type == UnitType.AI:
                if not self.is_repair_zero(src_unit, dst_unit) and not dst_unit.has_full_health():
                    return (True, ActionType.Repair)
            return (False, None)

        # If dst is enemy square, return true (this is the attack)
        if dst_unit.player != self.next_player:
            return (True, ActionType.Attack)

    def perform_move(self, coords : CoordPair) -> Tuple[bool, ActionType, str]:
        """Validate and perform a move expressed as a CoordPair."""
        is_valid, action_type = self.is_valid_move(coords)
        if is_valid:
            self.do_move_action(coords, action_type)
            return (True, action_type,"")
        return (False, None, "invalid move")

    def do_move_action(self, coords : CoordPair, action_type : ActionType):
        """Performs the action specified. Does not verify if move is valid or not."""
        if action_type == ActionType.SelfDestruct:
            self.perform_self_distruct(coords.src)
        elif action_type == ActionType.Move:
            self.set(coords.dst,self.get(coords.src))
            self.set(coords.src,None)
        elif action_type == ActionType.Attack:
            self.perform_fight(coords)
        elif action_type == ActionType.Repair:
            self.perform_repair(coords)        

    def next_turn(self):
        """Transitions game to the next turn."""
        self.next_player = self.next_player.next()
        self.turns_played += 1

    def generate_action_description(self, coords: CoordPair, action_type: ActionType) -> str:
        if action_type is ActionType.Move:
            return f"Move from {coords.src} to {coords.dst}"
        elif action_type is ActionType.Attack:
            return f"Attack by {coords.src} to {coords.dst}"
        elif action_type is ActionType.Repair:
            return f"Repair by {coords.src} to {coords.dst}"
        elif action_type is ActionType.SelfDestruct:
            return f"Self Destruct at {coords.src}"
        else:
            return f"Invalid move. src: {coords.src} - dist: {coords.dst}"

    def print_board(self) -> str:
        dim = self.options.dim
        coord = Coord()
        output = "\n   "
        for col in range(dim):
            coord.col = col
            label = coord.col_string()
            output += f"{label:^3} "
        output += "\n"
        for row in range(dim):
            coord.row = row
            label = coord.row_string()
            output += f"{label}: "
            for col in range(dim):
                coord.col = col
                unit = self.get(coord)
                if unit is None:
                    output += " .  "
                else:
                    output += f"{str(unit):^3} "
            output += "\n"
        return output

    def to_string(self) -> str:
        """Pretty text representation of the game."""
        output = ""
        output += f"Next player: {self.next_player.name}\n"
        output += f"Turns played: {self.turns_played}\n"
        output += self.print_board()
        return output

    def __str__(self) -> str:
        """Default string representation of a game."""
        return self.to_string()
    
    def is_valid_coord(self, coord: Coord) -> bool:
        """Check if a Coord is valid within out board dimensions."""
        dim = self.options.dim
        if coord.row < 0 or coord.row >= dim or coord.col < 0 or coord.col >= dim:
            return False
        return True

    def read_move(self) -> CoordPair:
        """Read a move from keyboard and return as a CoordPair."""
        while True:
            s = input(F'Player {self.next_player.name}, enter your move: ')
            coords = CoordPair.from_string(s)
            if coords is not None and self.is_valid_coord(coords.src) and self.is_valid_coord(coords.dst):
                return coords
            else:
                print('Invalid coordinates! Try again.')
    
    def human_turn(self):
        """Human player plays a move (or get via broker)."""
        if self.options.broker is not None:
            print("Getting next move with auto-retry from game broker...")
            while True:
                mv = self.get_move_from_broker()
                if mv is not None:
                    (success, action_type, result) = self.perform_move(mv)
                    print(f"Broker {self.next_player.name}: ",end='')
                    print(result)
                    if success:
                        output_file_data = {
                            "Player Name": f"Broker {self.next_player.name}",
                            "Turn Number": self.turns_played + 1,
                            "Action Taken": self.generate_action_description(mv, action_type),
                            "Current Board": f"\n{self.print_board()}"
                        }

                        self.dump_to_output_file(output_file_data)
                        self.next_turn()
                        break
                    else:
                        output_file_data = {
                            "Player Name": f"Broker {self.next_player.name}",
                            "Turn Number": self.turns_played + 1,
                            "Action Taken": self.generate_action_description(mv, action_type),
                            "Current Board": f"\n{self.print_board()}"
                        }

                        self.dump_to_output_file(output_file_data)
                sleep(0.1)
        else:
            while True:
                mv = self.read_move()
                (success, action_type, result) = self.perform_move(mv)
                if success:
                    print(f"Player {self.next_player.name}: ",end='')
                    print(result)

                    output_file_data = {
                        "Player Name": self.next_player.name,
                        "Turn Number": self.turns_played + 1,
                        "Action Taken": self.generate_action_description(mv, action_type),
                        "Current Board": f"\n{self.print_board()}"
                    }

                    self.dump_to_output_file(output_file_data)
                    self.next_turn()
                    break
                else:
                    output_file_data = {
                        "Player Name": self.next_player.name,
                        "Turn Number": self.turns_played + 1,
                        "Action Taken": self.generate_action_description(mv, action_type),
                        "Current Board": f"\n{self.print_board()}"
                    }

                    self.dump_to_output_file(output_file_data)
                    print("The move is not valid! Try again.")

    def computer_turn(self) -> CoordPair | None:
        """Computer plays a move."""
        
        output_file_data = {
            "Player Name": self.next_player.name,
            "Turn Number": self.turns_played + 1,
        }
        mv = self.suggest_move(output_file_data)
        if mv is not None:
            (success, action_type, result) = self.perform_move(mv)
            if success:
                print(f"Computer {self.next_player.name}: ",end='')
                print(result)

                output_file_data["Action Taken"] = self.generate_action_description(mv, action_type)
                output_file_data["Current Board"] = f"\n{self.print_board()}"

                self.dump_to_output_file(output_file_data)
                self.next_turn()
            else:
                output_file_data["Action Taken"] = self.generate_action_description(mv, action_type)
                output_file_data["Current Board"] = f"\n{self.print_board()}"

                self.dump_to_output_file(output_file_data)
        return mv

    def player_units(self, player: Player) -> Iterable[Tuple[Coord,Unit]]:
        """Iterates over all units belonging to a player."""
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None and unit.player == player:
                yield (coord,unit)

    def get_all_units(self) -> Iterable[Tuple[Coord,Unit]]:
        """Iterates over all units on board, regardless of who they belong to"""
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None:
                yield (coord,unit)

    def is_finished(self) -> bool:
        """Check if the game is over."""
        return self.has_winner() is not None

    def has_winner(self) -> Player | None:
        """Check if the game is over and returns winner"""
        if self.options.max_turns is not None and self.turns_played >= self.options.max_turns:
            self.dump_to_output_file({"Winner": f"Defender in {self.turns_played} turns"})
            return Player.Defender
        elif self._attacker_has_ai:
            if self._defender_has_ai:
                return None
            else:
                self.dump_to_output_file({"Winner": f"Attacker in {self.turns_played} turns"})
                return Player.Attacker    
        elif self._defender_has_ai:
            self.dump_to_output_file({"Winner": f"Defender in {self.turns_played} turns"})
            return Player.Defender
        else:
            self.dump_to_output_file({"Winner": f"Defender in {self.turns_played} turns"})
            return Player.Defender

    def move_candidates(self) -> Iterable[CoordPair, ActionType]:
        """Generate valid move candidates for the next player."""
        move = CoordPair()
        for (src,_) in self.player_units(self.next_player):
            move.src = src
            for dst in src.iter_adjacent():
                move.dst = dst
                is_valid, action_type = self.is_valid_move(move)
                if is_valid:
                    yield (move.clone(), action_type)
            move.dst = src
            yield (move.clone(), ActionType.SelfDestruct)

    def get_child_states(self) -> Iterable[CoordPair, Game]:
        """Given a current game state, generates all possible immediate child game states"""
        for (move, action_type) in self.move_candidates():
            child_state = self.clone()
            child_state.do_move_action(move, action_type)
            # child_state.score = child_state.calculate_heuristic() # No need to waste time calculating the score for all the states
            yield (move, child_state)

    def get_best_move_minimax(self) -> Tuple[int, CoordPair | None, float, float]:
        """Get best move for current player using minimax"""
        start_time = time()
        buffer_time = 0.2


        def alpha_beta_search(max_player: bool, curDepth: int, maxDepth: int, node:Game, alphaVal: int, betaVal: int ) -> Tuple[int, CoordPair | None]:
            if (curDepth - self.turns_played) == node.options.max_depth or (time() - start_time + buffer_time > self.options.max_time) or node.is_finished():
                hScore = node.calculate_heuristic
                return (hScore,None)
            if max_player:
                bestValue = float('-inf')
                for (move, child_state) in node.get_child_states():
                    child_state.next_turn()
                    child_value, _ = alpha_beta_search(False, curDepth + 1, maxDepth, child_state,alphaVal,betaVal)
                    if bestValue < child_value:
                        bestValue = child_value
                        bestMove= move
                    alphaVal = max(bestValue, alphaVal)
                    if betaVal <= alphaVal:
                        break
                return (bestValue, bestMove)
            else:
                bestValue = float('inf')
                for (move, child_state) in node.get_child_states():
                    child_state.next_turn()
                    child_value, _ = alpha_beta_search(True, curDepth + 1, maxDepth, child_state,alphaVal,betaVal)
                    if bestValue > child_value:
                        bestValue = child_value
                        bestMove = move
                    betaVal = min(bestValue, betaVal)
                    if betaVal <= alphaVal:
                        break
                return (bestValue, bestMove)

                

        def search(state: Game, currentDepth: int, maxDepth: int, maximizingPlayer: bool) -> Tuple[int, CoordPair | None]:
            nonlocal nodes_explored, total_depth, num_non_leaf_nodes
            if (currentDepth - self.turns_played) == maxDepth or (time() - start_time + buffer_time > self.options.max_time) or state.is_finished():
                score = state.calculate_heuristic()
                num_non_leaf_nodes -= 1
                return (score, None)
            
            if maximizingPlayer:
                value = float('-inf')
                best_move = None
                for (mv, child_state) in state.get_child_states():
                    child_state.next_turn()
                    child_value, _ = search(child_state, currentDepth + 1, maxDepth, False)
                    nodes_explored += 1
                    num_non_leaf_nodes += 1
                    total_depth += (currentDepth - self.turns_played + 1)
                    state.stats.evaluations_per_depth[currentDepth + 1] = state.stats.evaluations_per_depth.setdefault(currentDepth + 1, 0) + 1
                    if child_value > value:
                        value = child_value
                        best_move = mv
                return (value, best_move)
            else:
                value = float('inf')
                best_move = None
                for (mv, child_state) in state.get_child_states():
                    child_state.next_turn()
                    child_value, _ = search(child_state, currentDepth + 1, maxDepth, True)
                    nodes_explored += 1
                    num_non_leaf_nodes += 1
                    total_depth += (currentDepth - self.turns_played + 1)
                    state.stats.evaluations_per_depth[currentDepth + 1] = state.stats.evaluations_per_depth.setdefault(currentDepth + 1, 0) + 1
                    if child_value < value:
                        value = child_value
                        best_move = mv
                return (value, best_move)
        
        max_depth = 1
        best_move = None
        maximize = self.next_player == Player.Attacker
        while (time() - start_time + buffer_time < self.options.max_time) and max_depth <= self.options.max_depth:
            total_depth = 0
            nodes_explored = 1
            num_non_leaf_nodes = 0
            score, best_move = search(self, self.turns_played, max_depth, maximize) if not(self.options.alpha_beta) else alpha_beta_search(maximize, self.turns_played, max_depth, self, MIN_HEURISTIC_SCORE, MAX_HEURISTIC_SCORE)
            average_depth = total_depth / nodes_explored
            average_branching_factor = (nodes_explored - 1) / num_non_leaf_nodes if num_non_leaf_nodes != 0 else 0
            max_depth += 1
        return (score, best_move, average_depth, average_branching_factor)

    def random_move(self) -> Tuple[int, CoordPair | None, float]:
        """Returns a random move."""
        move_candidates = list()
        for (move, _) in self.move_candidates():
            move_candidates.append(move)
        random.shuffle(move_candidates)
        if len(move_candidates) > 0:
            return (0, move_candidates[0], 1)
        else:
            return (0, None, 0)
        
    def calculate_heuristic(self) -> int:
        """Calculates heuristic for current game state"""
        # TODO: use actual heuristic for e1 and e2
        if self.options.heuristic == "e0":
            # (3VP1 + 3TP1 + 3FP1 + 3PP1 + 9999AiP1) - (3VP2 + 3TP2 + 3FP2 + 3PP2 + 9999AiP2)
            # Where V = number of virus, T = number of tech, 
            # F = number of firewall, P = number of program, Ai = number of AI
            # and P1 is player 1 (attacker), P2 is player 2 (defender)
            score = 0
            for (_, unit) in self.get_all_units():
                # Increment for attacker
                if unit.player == Player.Attacker:
                    if (unit.type == UnitType.AI):
                        score += 9999
                    else:
                        score += 3 
                # Decrement for defender
                if unit.player == Player.Defender:
                    if (unit.type == UnitType.AI):
                        score -= 9999
                    else:
                        score -= 3 
            return score 

        if self.options.heuristic == "e1":
            return 0
        
        if self.options.heuristic == "e2":
            score = 0
            for (_, unit) in self.get_all_units():
                # Increment for attacker
                if unit.player == Player.Attacker:

                    if unit.type == UnitType.AI:
                        score += (1000*(unit.health))
                    elif unit.type == UnitType.Virus:
                        score += (30*(unit.health))
                    else:
                        score += 10*unit.health
                
                # Decrement for defender
                if unit.player == Player.Defender:
                    
                    if unit.type == UnitType.AI:
                        score -= (1000*(unit.health))
                    elif unit.type == UnitType.Tech:
                        score -= (30*(unit.health))
                    else:
                        score -= 10*unit.health
            return score 
        
    def suggest_move(self, output_file_data: dict[str, str]) -> CoordPair | None:
        """Suggest the next move using minimax alpha beta."""
        start_time = datetime.now()
        (score, move, avg_depth, avg_branching_factor) = self.get_best_move_minimax()
        elapsed_seconds = (datetime.now() - start_time).total_seconds()
        
        # Check if AI took too long
        if elapsed_seconds > float(self.options.max_time):
            raise RuntimeError

        self.stats.total_seconds += elapsed_seconds
        print(f"Heuristic score: {score}")
        print(f"Average recursive depth: {avg_depth:0.1f}")
        print(f"Evals per depth: ",end='')
        for k in sorted(self.stats.evaluations_per_depth.keys()):
            print(f"{k}:{self.stats.evaluations_per_depth[k]} ",end='')
        print()
        total_evals = sum(self.stats.evaluations_per_depth.values())
        if self.stats.total_seconds > 0:
            print(f"Eval perf.: {total_evals/self.stats.total_seconds/1000:0.1f}k/s")
        print(f"Elapsed time: {elapsed_seconds:0.1f}s")

        output_file_data["Duration of action (seconds)"] = f"{elapsed_seconds:0.1f}"
        output_file_data["Heuristic score"] = score
        output_file_data["Cumulative evals"] = sum(self.stats.evaluations_per_depth.values())
        output_file_data["Cumulative evals by depth"] = "".join([f"{k}:{self.stats.evaluations_per_depth[k]} " for k in sorted(self.stats.evaluations_per_depth.keys())])
        output_file_data["Cumulative % evals by depth"] = "".join([f"{k}:{round(self.stats.evaluations_per_depth[k] * 100/total_evals, 2)}% " for k in sorted(self.stats.evaluations_per_depth.keys())])
        output_file_data["Average Branching factor"] = f"{avg_branching_factor:0.1f}"

        return move

    def post_move_to_broker(self, move: CoordPair):
        """Send a move to the game broker."""
        if self.options.broker is None:
            return
        data = {
            "from": {"row": move.src.row, "col": move.src.col},
            "to": {"row": move.dst.row, "col": move.dst.col},
            "turn": self.turns_played
        }
        try:
            r = requests.post(self.options.broker, json=data)
            if r.status_code == 200 and r.json()['success'] and r.json()['data'] == data:
                # print(f"Sent move to broker: {move}")
                pass
            else:
                print(f"Broker error: status code: {r.status_code}, response: {r.json()}")
        except Exception as error:
            print(f"Broker error: {error}")

    def get_move_from_broker(self) -> CoordPair | None:
        """Get a move from the game broker."""
        if self.options.broker is None:
            return None
        headers = {'Accept': 'application/json'}
        try:
            r = requests.get(self.options.broker, headers=headers)
            if r.status_code == 200 and r.json()['success']:
                data = r.json()['data']
                if data is not None:
                    if data['turn'] == self.turns_played+1:
                        move = CoordPair(
                            Coord(data['from']['row'],data['from']['col']),
                            Coord(data['to']['row'],data['to']['col'])
                        )
                        print(f"Got move from broker: {move}")
                        return move
                    else:
                        # print("Got broker data for wrong turn.")
                        # print(f"Wanted {self.turns_played+1}, got {data['turn']}")
                        pass
                else:
                    # print("Got no data from broker")
                    pass
            else:
                print(f"Broker error: status code: {r.status_code}, response: {r.json()}")
        except Exception as error:
            print(f"Broker error: {error}")
        return None

##############################################################################################################

def main():
    # parse command line arguments
    parser = argparse.ArgumentParser(
        prog='ai_wargame',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--max_depth', type=int, help='maximum search depth')
    parser.add_argument('--max_time', type=float, help='maximum search time')
    parser.add_argument('--game_type', type=str, default="manual", help='game type: auto|attacker|defender|manual')
    parser.add_argument('--broker', type=str, help='play via a game broker')
    parser.add_argument('--heuristic', type=str, default="e0", help='heuristic type: e0|e1|e2')
    parser.add_argument('--alpha_beta', default=True, type=lambda x: (str(x).lower() == 'true'), help='Use alpha beta: True|False')
    parser.add_argument('--max_turns', type=int, default="100", help='Max number of turns')
    args = parser.parse_args()



    #Intro to AI Wargame
    print("Welcome to the AI Wargame!")
    
    while True:
        #Check to see if user would like default settings for the game or customize their own settings
        rules = input("Would you like to use the default or custom settings for the game setup? (d|c): ")
        if rules is not None and (rules == 'c' or rules == 'd') :

            #default rules have been chosen, will create the game with all default values
            if rules == 'd':
                print("\nWe will setup the game with default settings! GLHF!")
                break    

            #custom rules have been chosen, user will chose their values
            elif rules == 'c':
                print("Custom rules!")
                
                #choosing game type
                while True:
                    gtype = input("Please enter the game type (auto|attacker|defender|manual): ")
                    if gtype is not None and (gtype == 'auto' or gtype == 'attacker' or gtype == 'defender' or gtype == 'manual' ):

                        #after check if game type is of proper format. it is parsed using the argument parser and stored
                        args.game_type = gtype

                        #max number of turns
                        while True:
                            maxTurn = input("Please input the max number of turns you would like the game to run (postive integer):")
                            if maxTurn is not None and maxTurn.isnumeric() and int(maxTurn)>0:
                                args.max_turns = int(maxTurn)
                                break
                            else:
                                print("Invalid value for number of turns entered.")                            
                        
                        
                        #if there are AI in the game (any game type other than manual)
                        if gtype != 'manual':
                            
                            #choosing max Depth for AI
                            while True :
                                mdepth = input("Please enter the max search depth for the Computer opponent (positive Integer greater than 1): ") 
                                if mdepth is not None and mdepth.isnumeric() and int(mdepth) > 1:
                                    args.max_depth = int(mdepth)
                                    break
                                else:
                                    print("Invalid entry for max search depth") #search Depth invalid
                            
                            #choosing max search Time for AI
                            while True :
                                mtime = input("Please enter the max time allowed for AI to search for next move (Positive number greater than 0): ")
                                try:
                                    float(mtime)
                                    if mtime is not None and float(mtime) > 0:
                                        args.max_time = float(mtime)
                                        break
                                    else:
                                        print("Invalid entry for max search time") #search Time invalid
                                except ValueError:
                                    print("Invalid entry for max search time") #search Time invalid
                                    

                        ##FOR THE BROKER: not sure what to check for here as the url entry. kept pretty simple. 
                        ## used validators to check if entry is indeed a URL. regardless of what the URL points to

                        #choosing broker URL
                        while True :
                            broker = input("Please enter the broker URL, or enter null for no broker: ")
                            if broker is not None:
                                if broker == "null":
                                    args.broker = None
                                    break
                                if validators.url(broker):
                                    args.broker = broker
                                    break
                            else:
                                print("This is an invalid URL for the broker.")
                        break
                    else :
                        print("Invalid entry for Game Type. Please try again.") #game type invalid.
            break
        else :
            print("Invalid entry for game setup please try again.") #default or custom settings choice is invalid.

    # parse the game type
    if args.game_type == "attacker":
        game_type = GameType.AttackerVsComp
    elif args.game_type == "defender":
        game_type = GameType.CompVsDefender
    elif args.game_type == "manual":
        game_type = GameType.AttackerVsDefender
    else:
        game_type = GameType.CompVsComp

    # set up game options
    options = Options(game_type=game_type)

    # override class defaults via command line options
    if args.max_depth is not None:
        options.max_depth = args.max_depth
    if args.max_time is not None:
        options.max_time = args.max_time
    if args.broker is not None:
        options.broker = args.broker
    if args.heuristic is not None and game_type != GameType.AttackerVsDefender:
        options.heuristic = args.heuristic
    if args.alpha_beta is not None:
        options.alpha_beta = args.alpha_beta
    if args.max_turns is not None:
        options.max_turns = args.max_turns

    # create a new game
    game = Game(options=options)

    # Create log file
    output_file_data = {
        "Section": "Game Parameters",
        "Timeout Value (seconds)": game.options.max_time,
        "Max Numbers of Turns": game.options.max_turns,
        "Play Modes": GameTypeConverter.convert_game_type(game.options.game_type)
    }

    if game.options.game_type != GameType.AttackerVsDefender:
        output_file_data["Alpha-Beta"] = "on" if game.options.alpha_beta else "off"
        output_file_data["Heuristic"] = game.options.heuristic
    
    output_file_data["Initial Board"] = f"\n{game.print_board()}"
    game.dump_to_output_file(output_file_data, append=False)

    # the main game loop
    while True:
        print()
        print(game)
        winner = game.has_winner()
        if winner is not None:
            print(f"{winner.name} wins!")
            break
        if game.options.game_type == GameType.AttackerVsDefender:
            game.human_turn()
        elif game.options.game_type == GameType.AttackerVsComp and game.next_player == Player.Attacker:
            game.human_turn()
        elif game.options.game_type == GameType.CompVsDefender and game.next_player == Player.Defender:
            game.human_turn()
        else:
            player = game.next_player
            try:
                move = game.computer_turn()
                if move is not None:
                    game.post_move_to_broker(move)
                else:
                    print("Computer doesn't know what to do!!!")
                    exit(1)
            except RuntimeError:
                print(f"The computer {player.name} took too long to choose a move!")
                game.next_turn()
                print(f"{game.next_player.name} wins!")
                break

##############################################################################################################

if __name__ == '__main__':
    main()
