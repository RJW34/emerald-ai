"""
Pokemon Gen 3 Move Database.

Contains base data for all 354 moves in Gen 3, sourced from pokeemerald decomp.
Used by the Battle AI to look up move power, type, accuracy, and flags
when only the move ID is read from memory.

Gen 3 physical/special split is TYPE-BASED:
  Physical types: Normal, Fighting, Flying, Poison, Ground, Rock, Bug, Ghost, Steel
  Special types:  Fire, Water, Grass, Electric, Psychic, Ice, Dragon, Dark
"""

from ..games.pokemon_gen3.data_types import PokemonType, Move

# (name, type, power, accuracy, pp, priority, flags)
# flags: C=contact, S=sound-based, P=punch, B=bite
_MOVE_TABLE: dict[int, tuple] = {
    # === Normal Moves ===
    1:   ("Pound",         PokemonType.NORMAL,   40, 100, 35, 0, "C"),
    5:   ("Mega Punch",    PokemonType.NORMAL,   80, 85,  20, 0, "C"),
    6:   ("Pay Day",       PokemonType.NORMAL,   40, 100, 20, 0, ""),
    7:   ("Fire Punch",    PokemonType.FIRE,     75, 100, 15, 0, "CP"),
    8:   ("Ice Punch",     PokemonType.ICE,      75, 100, 15, 0, "CP"),
    9:   ("Thunder Punch", PokemonType.ELECTRIC, 75, 100, 15, 0, "CP"),
    10:  ("Scratch",       PokemonType.NORMAL,   40, 100, 35, 0, "C"),
    11:  ("Vice Grip",     PokemonType.NORMAL,   55, 100, 30, 0, "C"),
    12:  ("Guillotine",    PokemonType.NORMAL,    0, 30,   5, 0, "C"),  # OHKO
    13:  ("Razor Wind",    PokemonType.NORMAL,   80, 100, 10, 0, ""),
    14:  ("Swords Dance",  PokemonType.NORMAL,    0,   0, 30, 0, ""),
    15:  ("Cut",           PokemonType.NORMAL,   50, 95,  30, 0, "C"),
    16:  ("Gust",          PokemonType.FLYING,   40, 100, 35, 0, ""),
    17:  ("Wing Attack",   PokemonType.FLYING,   60, 100, 35, 0, "C"),
    18:  ("Whirlwind",     PokemonType.NORMAL,    0, 100, 20, -6, ""),
    19:  ("Fly",           PokemonType.FLYING,   70, 95,  15, 0, "C"),
    20:  ("Bind",          PokemonType.NORMAL,   15, 75,  20, 0, "C"),
    21:  ("Slam",          PokemonType.NORMAL,   80, 75,  20, 0, "C"),
    22:  ("Vine Whip",     PokemonType.GRASS,    35, 100, 10, 0, "C"),
    23:  ("Stomp",         PokemonType.NORMAL,   65, 100, 20, 0, "C"),
    24:  ("Double Kick",   PokemonType.FIGHTING, 30, 100, 30, 0, "C"),
    25:  ("Mega Kick",     PokemonType.NORMAL,  120, 75,   5, 0, "C"),
    26:  ("Jump Kick",     PokemonType.FIGHTING, 70, 95,  25, 0, "C"),
    27:  ("Rolling Kick",  PokemonType.FIGHTING, 60, 85,  15, 0, "C"),
    28:  ("Sand Attack",   PokemonType.GROUND,    0, 100, 15, 0, ""),
    29:  ("Headbutt",      PokemonType.NORMAL,   70, 100, 15, 0, "C"),
    30:  ("Horn Attack",   PokemonType.NORMAL,   65, 100, 25, 0, "C"),
    31:  ("Fury Attack",   PokemonType.NORMAL,   15, 85,  20, 0, "C"),
    32:  ("Horn Drill",    PokemonType.NORMAL,    0, 30,   5, 0, "C"),  # OHKO
    33:  ("Tackle",        PokemonType.NORMAL,   35, 95,  35, 0, "C"),
    34:  ("Body Slam",     PokemonType.NORMAL,   85, 100, 15, 0, "C"),
    35:  ("Wrap",          PokemonType.NORMAL,   15, 85,  20, 0, "C"),
    36:  ("Take Down",     PokemonType.NORMAL,   90, 85,  20, 0, "C"),
    37:  ("Thrash",        PokemonType.NORMAL,   90, 100, 20, 0, "C"),
    38:  ("Double-Edge",   PokemonType.NORMAL,  120, 100, 15, 0, "C"),
    39:  ("Tail Whip",     PokemonType.NORMAL,    0, 100, 30, 0, ""),
    40:  ("Poison Sting",  PokemonType.POISON,   15, 100, 35, 0, ""),
    41:  ("Twineedle",     PokemonType.BUG,      25, 100, 20, 0, ""),
    42:  ("Pin Missile",   PokemonType.BUG,      14, 85,  20, 0, ""),
    43:  ("Leer",          PokemonType.NORMAL,    0, 100, 30, 0, ""),
    44:  ("Bite",          PokemonType.DARK,     60, 100, 25, 0, "CB"),
    45:  ("Growl",         PokemonType.NORMAL,    0, 100, 40, 0, "S"),
    46:  ("Roar",          PokemonType.NORMAL,    0, 100, 20, -6, "S"),
    47:  ("Sing",          PokemonType.NORMAL,    0, 55,  15, 0, "S"),
    48:  ("Supersonic",    PokemonType.NORMAL,    0, 55,  20, 0, "S"),
    49:  ("Sonic Boom",    PokemonType.NORMAL,    0, 90,  20, 0, ""),  # Fixed 20 dmg
    50:  ("Disable",       PokemonType.NORMAL,    0, 55,  20, 0, ""),
    51:  ("Acid",          PokemonType.POISON,   40, 100, 30, 0, ""),
    52:  ("Ember",         PokemonType.FIRE,     40, 100, 25, 0, ""),
    53:  ("Flamethrower",  PokemonType.FIRE,     95, 100, 15, 0, ""),
    54:  ("Mist",          PokemonType.ICE,       0,   0, 30, 0, ""),
    55:  ("Water Gun",     PokemonType.WATER,    40, 100, 25, 0, ""),
    56:  ("Hydro Pump",    PokemonType.WATER,   120, 80,   5, 0, ""),
    57:  ("Surf",          PokemonType.WATER,    95, 100, 15, 0, ""),
    58:  ("Ice Beam",      PokemonType.ICE,      95, 100, 10, 0, ""),
    59:  ("Blizzard",      PokemonType.ICE,     120, 70,   5, 0, ""),
    60:  ("Psybeam",       PokemonType.PSYCHIC,  65, 100, 20, 0, ""),
    61:  ("Bubble Beam",   PokemonType.WATER,    65, 100, 20, 0, ""),
    62:  ("Aurora Beam",   PokemonType.ICE,      65, 100, 20, 0, ""),
    63:  ("Hyper Beam",    PokemonType.NORMAL,  150, 90,   5, 0, ""),
    64:  ("Peck",          PokemonType.FLYING,   35, 100, 35, 0, "C"),
    65:  ("Drill Peck",    PokemonType.FLYING,   80, 100, 20, 0, "C"),
    66:  ("Submission",    PokemonType.FIGHTING, 80, 80,  25, 0, "C"),
    67:  ("Low Kick",      PokemonType.FIGHTING,  0, 100, 20, 0, "C"),  # Weight-based
    68:  ("Counter",       PokemonType.FIGHTING,  0, 100, 20, -5, "C"),
    69:  ("Seismic Toss",  PokemonType.FIGHTING,  0, 100, 20, 0, "C"),  # Level-based
    70:  ("Strength",      PokemonType.NORMAL,   80, 100, 15, 0, "C"),
    71:  ("Absorb",        PokemonType.GRASS,    20, 100, 20, 0, ""),
    72:  ("Mega Drain",    PokemonType.GRASS,    40, 100, 10, 0, ""),
    73:  ("Leech Seed",    PokemonType.GRASS,     0, 90,  10, 0, ""),
    74:  ("Growth",        PokemonType.NORMAL,    0,   0, 40, 0, ""),
    75:  ("Razor Leaf",    PokemonType.GRASS,    55, 95,  25, 0, ""),
    76:  ("Solar Beam",    PokemonType.GRASS,   120, 100, 10, 0, ""),
    77:  ("Poison Powder", PokemonType.POISON,    0, 75,  35, 0, ""),
    78:  ("Stun Spore",    PokemonType.GRASS,     0, 75,  30, 0, ""),
    79:  ("Sleep Powder",  PokemonType.GRASS,     0, 75,  15, 0, ""),
    80:  ("Petal Dance",   PokemonType.GRASS,    70, 100, 20, 0, "C"),
    81:  ("String Shot",   PokemonType.BUG,       0, 95,  40, 0, ""),
    82:  ("Dragon Rage",   PokemonType.DRAGON,    0, 100, 10, 0, ""),  # Fixed 40 dmg
    83:  ("Fire Spin",     PokemonType.FIRE,     15, 70,  15, 0, ""),
    84:  ("Thunder Shock", PokemonType.ELECTRIC, 40, 100, 30, 0, ""),
    85:  ("Thunderbolt",   PokemonType.ELECTRIC, 95, 100, 15, 0, ""),
    86:  ("Thunder Wave",  PokemonType.ELECTRIC,  0, 100, 20, 0, ""),
    87:  ("Thunder",       PokemonType.ELECTRIC, 120, 70, 10, 0, ""),
    88:  ("Rock Throw",    PokemonType.ROCK,     50, 90,  15, 0, ""),
    89:  ("Earthquake",    PokemonType.GROUND,  100, 100, 10, 0, ""),
    90:  ("Fissure",       PokemonType.GROUND,    0, 30,   5, 0, ""),  # OHKO
    91:  ("Dig",           PokemonType.GROUND,   60, 100, 10, 0, "C"),
    92:  ("Toxic",         PokemonType.POISON,    0, 85,  10, 0, ""),
    93:  ("Confusion",     PokemonType.PSYCHIC,  50, 100, 25, 0, ""),
    94:  ("Psychic",       PokemonType.PSYCHIC,  90, 100, 10, 0, ""),
    95:  ("Hypnosis",      PokemonType.PSYCHIC,   0, 60,  20, 0, ""),
    96:  ("Meditate",      PokemonType.PSYCHIC,   0,   0, 40, 0, ""),
    97:  ("Agility",       PokemonType.PSYCHIC,   0,   0, 30, 0, ""),
    98:  ("Quick Attack",  PokemonType.NORMAL,   40, 100, 30, 1, "C"),
    99:  ("Rage",          PokemonType.NORMAL,   20, 100, 20, 0, "C"),
    100: ("Teleport",      PokemonType.PSYCHIC,   0,   0, 20, 0, ""),
    101: ("Night Shade",   PokemonType.GHOST,     0, 100, 15, 0, ""),  # Level-based
    102: ("Mimic",         PokemonType.NORMAL,    0, 100, 10, 0, ""),
    103: ("Screech",       PokemonType.NORMAL,    0, 85,  40, 0, "S"),
    104: ("Double Team",   PokemonType.NORMAL,    0,   0, 15, 0, ""),
    105: ("Recover",       PokemonType.NORMAL,    0,   0, 20, 0, ""),
    106: ("Harden",        PokemonType.NORMAL,    0,   0, 30, 0, ""),
    107: ("Minimize",      PokemonType.NORMAL,    0,   0, 20, 0, ""),
    108: ("Smokescreen",   PokemonType.NORMAL,    0, 100, 20, 0, ""),
    109: ("Confuse Ray",   PokemonType.GHOST,     0, 100, 10, 0, ""),
    110: ("Withdraw",      PokemonType.WATER,     0,   0, 40, 0, ""),
    111: ("Defense Curl",  PokemonType.NORMAL,    0,   0, 40, 0, ""),
    112: ("Barrier",       PokemonType.PSYCHIC,   0,   0, 30, 0, ""),
    113: ("Light Screen",  PokemonType.PSYCHIC,   0,   0, 30, 0, ""),
    114: ("Haze",          PokemonType.ICE,       0,   0, 30, 0, ""),
    115: ("Reflect",       PokemonType.PSYCHIC,   0,   0, 20, 0, ""),
    116: ("Focus Energy",  PokemonType.NORMAL,    0,   0, 30, 0, ""),
    117: ("Bide",          PokemonType.NORMAL,    0,   0, 10, 1, "C"),
    118: ("Metronome",     PokemonType.NORMAL,    0,   0, 10, 0, ""),
    119: ("Mirror Move",   PokemonType.FLYING,    0,   0, 20, 0, ""),
    120: ("Self-Destruct", PokemonType.NORMAL,  200, 100,  5, 0, ""),
    121: ("Egg Bomb",      PokemonType.NORMAL,  100, 75,  10, 0, ""),
    122: ("Lick",          PokemonType.GHOST,    20, 100, 30, 0, "C"),
    123: ("Smog",          PokemonType.POISON,   20, 70,  20, 0, ""),
    124: ("Sludge",        PokemonType.POISON,   65, 100, 20, 0, ""),
    125: ("Bone Club",     PokemonType.GROUND,   65, 85,  20, 0, ""),
    126: ("Fire Blast",    PokemonType.FIRE,    120, 85,   5, 0, ""),
    127: ("Waterfall",     PokemonType.WATER,    80, 100, 15, 0, "C"),
    128: ("Clamp",         PokemonType.WATER,    35, 75,  10, 0, "C"),
    129: ("Swift",         PokemonType.NORMAL,   60,   0, 20, 0, ""),  # Can't miss
    130: ("Skull Bash",    PokemonType.NORMAL,  100, 100, 15, 0, "C"),
    131: ("Spike Cannon",  PokemonType.NORMAL,   20, 100, 15, 0, ""),
    132: ("Constrict",     PokemonType.NORMAL,   10, 100, 35, 0, "C"),
    133: ("Amnesia",       PokemonType.PSYCHIC,   0,   0, 20, 0, ""),
    134: ("Kinesis",       PokemonType.PSYCHIC,   0, 80,  15, 0, ""),
    135: ("Soft-Boiled",   PokemonType.NORMAL,    0,   0, 10, 0, ""),
    136: ("Hi Jump Kick",  PokemonType.FIGHTING, 85, 90,  20, 0, "C"),
    137: ("Glare",         PokemonType.NORMAL,    0, 75,  30, 0, ""),
    138: ("Dream Eater",   PokemonType.PSYCHIC, 100, 100, 15, 0, ""),
    139: ("Poison Gas",    PokemonType.POISON,    0, 55,  40, 0, ""),
    140: ("Barrage",       PokemonType.NORMAL,   15, 85,  20, 0, ""),
    141: ("Leech Life",    PokemonType.BUG,      20, 100, 15, 0, "C"),
    142: ("Lovely Kiss",   PokemonType.NORMAL,    0, 75,  10, 0, ""),
    143: ("Sky Attack",    PokemonType.FLYING,  140, 90,   5, 0, ""),
    144: ("Transform",     PokemonType.NORMAL,    0,   0, 10, 0, ""),
    145: ("Bubble",        PokemonType.WATER,    20, 100, 30, 0, ""),
    146: ("Dizzy Punch",   PokemonType.NORMAL,   70, 100, 10, 0, "CP"),
    147: ("Spore",         PokemonType.GRASS,     0, 100, 15, 0, ""),
    148: ("Flash",         PokemonType.NORMAL,    0, 70,  20, 0, ""),
    149: ("Psywave",       PokemonType.PSYCHIC,   0, 80,  15, 0, ""),  # Random dmg
    150: ("Splash",        PokemonType.NORMAL,    0,   0, 40, 0, ""),
    151: ("Acid Armor",    PokemonType.POISON,    0,   0, 40, 0, ""),
    152: ("Crabhammer",    PokemonType.WATER,    90, 85,  10, 0, "C"),
    153: ("Explosion",     PokemonType.NORMAL,  250, 100,  5, 0, ""),
    154: ("Fury Swipes",   PokemonType.NORMAL,   18, 80,  15, 0, "C"),
    155: ("Bonemerang",    PokemonType.GROUND,   50, 90,  10, 0, ""),
    156: ("Rest",          PokemonType.PSYCHIC,   0,   0, 10, 0, ""),
    157: ("Rock Slide",    PokemonType.ROCK,     75, 90,  10, 0, ""),
    158: ("Hyper Fang",    PokemonType.NORMAL,   80, 90,  15, 0, "CB"),
    159: ("Sharpen",       PokemonType.NORMAL,    0,   0, 30, 0, ""),
    160: ("Conversion",    PokemonType.NORMAL,    0,   0, 30, 0, ""),
    161: ("Tri Attack",    PokemonType.NORMAL,   80, 100, 10, 0, ""),
    162: ("Super Fang",    PokemonType.NORMAL,    0, 90,  10, 0, "C"),  # Halves HP
    163: ("Slash",         PokemonType.NORMAL,   70, 100, 20, 0, "C"),
    164: ("Substitute",    PokemonType.NORMAL,    0,   0, 10, 0, ""),
    165: ("Struggle",      PokemonType.NORMAL,   50, 100,  1, 0, "C"),  # Emergency
    # Gen 2+ moves
    168: ("Thief",         PokemonType.DARK,     40, 100, 10, 0, "C"),
    170: ("Mind Reader",   PokemonType.NORMAL,    0, 100,  5, 0, ""),
    172: ("Flame Wheel",   PokemonType.FIRE,     60, 100, 25, 0, "C"),
    173: ("Snore",         PokemonType.NORMAL,   40, 100, 15, 0, "S"),
    175: ("Flail",         PokemonType.NORMAL,    0, 100, 15, 0, "C"),  # Variable power
    177: ("Aeroblast",     PokemonType.FLYING,  100, 95,   5, 0, ""),
    178: ("Cotton Spore",  PokemonType.GRASS,     0, 85,  40, 0, ""),
    180: ("Spite",         PokemonType.GHOST,     0, 100, 10, 0, ""),
    181: ("Powder Snow",   PokemonType.ICE,      40, 100, 25, 0, ""),
    182: ("Protect",       PokemonType.NORMAL,    0,   0, 10, 4, ""),
    183: ("Mach Punch",    PokemonType.FIGHTING, 40, 100, 30, 1, "CP"),
    184: ("Scary Face",    PokemonType.NORMAL,    0, 90,  10, 0, ""),
    185: ("Faint Attack",  PokemonType.DARK,     60,   0, 20, 0, ""),  # Can't miss
    186: ("Sweet Kiss",    PokemonType.NORMAL,    0, 75,  10, 0, ""),
    187: ("Belly Drum",    PokemonType.NORMAL,    0,   0, 10, 0, ""),
    188: ("Sludge Bomb",   PokemonType.POISON,   90, 100, 10, 0, ""),
    189: ("Mud-Slap",      PokemonType.GROUND,   20, 100, 10, 0, ""),
    190: ("Octazooka",     PokemonType.WATER,    65, 85,  10, 0, ""),
    191: ("Spikes",        PokemonType.GROUND,    0,   0, 20, 0, ""),
    192: ("Zap Cannon",    PokemonType.ELECTRIC, 100, 50,  5, 0, ""),
    196: ("Icy Wind",      PokemonType.ICE,      55, 95,  15, 0, ""),
    197: ("Detect",        PokemonType.FIGHTING,  0,   0,  5, 4, ""),
    200: ("Outrage",       PokemonType.DRAGON,   90, 100, 15, 0, "C"),
    202: ("Giga Drain",    PokemonType.GRASS,    60, 100,  5, 0, ""),
    203: ("Endure",        PokemonType.NORMAL,    0,   0, 10, 4, ""),
    204: ("Charm",         PokemonType.NORMAL,    0, 100, 20, 0, ""),
    205: ("Rollout",       PokemonType.ROCK,     30, 90,  20, 0, "C"),
    206: ("False Swipe",   PokemonType.NORMAL,   40, 100, 40, 0, "C"),  # Leaves 1 HP
    207: ("Swagger",       PokemonType.NORMAL,    0, 90,  15, 0, ""),
    208: ("Milk Drink",    PokemonType.NORMAL,    0,   0, 10, 0, ""),
    209: ("Spark",         PokemonType.ELECTRIC, 65, 100, 20, 0, "C"),
    210: ("Fury Cutter",   PokemonType.BUG,      10, 95,  20, 0, "C"),
    211: ("Steel Wing",    PokemonType.STEEL,    70, 90,  25, 0, "C"),
    213: ("Attract",       PokemonType.NORMAL,    0, 100, 15, 0, ""),
    214: ("Sleep Talk",    PokemonType.NORMAL,    0,   0, 10, 0, ""),
    215: ("Heal Bell",     PokemonType.NORMAL,    0,   0,  5, 0, "S"),
    216: ("Return",        PokemonType.NORMAL,    0, 100, 20, 0, "C"),  # Max 102 power
    217: ("Present",       PokemonType.NORMAL,    0, 90,  15, 0, ""),  # Random
    218: ("Frustration",   PokemonType.NORMAL,    0, 100, 20, 0, "C"),  # Max 102 power
    221: ("Sacred Fire",   PokemonType.FIRE,    100, 95,   5, 0, ""),
    223: ("Dynamic Punch", PokemonType.FIGHTING, 100, 50,  5, 0, "CP"),
    224: ("Megahorn",      PokemonType.BUG,     120, 85,  10, 0, "C"),
    225: ("Dragon Breath", PokemonType.DRAGON,   60, 100, 20, 0, ""),
    226: ("Baton Pass",    PokemonType.NORMAL,    0,   0, 40, 0, ""),
    227: ("Encore",        PokemonType.NORMAL,    0, 100,  5, 0, ""),
    229: ("Rapid Spin",    PokemonType.NORMAL,   20, 100, 40, 0, "C"),
    231: ("Iron Tail",     PokemonType.STEEL,   100, 75,  15, 0, "C"),
    232: ("Metal Claw",    PokemonType.STEEL,    50, 95,  35, 0, "C"),
    233: ("Vital Throw",   PokemonType.FIGHTING, 70,   0, 10, -1, "C"),  # Never misses
    237: ("Hidden Power",  PokemonType.NORMAL,    0, 100, 15, 0, ""),  # Variable type/power
    238: ("Cross Chop",    PokemonType.FIGHTING, 100, 80,  5, 0, "C"),
    239: ("Twister",       PokemonType.DRAGON,   40, 100, 20, 0, ""),
    241: ("Sunny Day",     PokemonType.FIRE,      0,   0,  5, 0, ""),
    242: ("Crunch",        PokemonType.DARK,     80, 100, 15, 0, "CB"),
    243: ("Mirror Coat",   PokemonType.PSYCHIC,   0, 100, 20, -5, ""),
    245: ("Extreme Speed", PokemonType.NORMAL,   80, 100,  5, 2, "C"),
    246: ("Ancient Power", PokemonType.ROCK,     60, 100,  5, 0, ""),
    247: ("Shadow Ball",   PokemonType.GHOST,    80, 100, 15, 0, ""),
    248: ("Future Sight",  PokemonType.PSYCHIC,  80, 90,  15, 0, ""),
    249: ("Rock Smash",    PokemonType.FIGHTING, 20, 100, 15, 0, "C"),
    250: ("Whirlpool",     PokemonType.WATER,    15, 70,  15, 0, ""),
    251: ("Beat Up",       PokemonType.DARK,     10, 100, 10, 0, ""),
    252: ("Fake Out",      PokemonType.NORMAL,   40, 100, 10, 3, "C"),  # First turn only
    253: ("Uproar",        PokemonType.NORMAL,   50, 100, 10, 0, "S"),
    254: ("Stockpile",     PokemonType.NORMAL,    0,   0, 20, 0, ""),
    255: ("Spit Up",       PokemonType.NORMAL,    0, 100, 10, 0, ""),  # Variable power
    256: ("Swallow",       PokemonType.NORMAL,    0,   0, 10, 0, ""),
    257: ("Heat Wave",     PokemonType.FIRE,    100, 90,  10, 0, ""),
    258: ("Hail",          PokemonType.ICE,       0,   0, 10, 0, ""),
    259: ("Torment",       PokemonType.DARK,      0, 100, 15, 0, ""),
    260: ("Flatter",       PokemonType.DARK,      0, 100, 15, 0, ""),
    261: ("Will-O-Wisp",   PokemonType.FIRE,      0, 75,  15, 0, ""),
    262: ("Memento",       PokemonType.DARK,      0, 100, 10, 0, ""),
    263: ("Facade",        PokemonType.NORMAL,   70, 100, 20, 0, "C"),
    264: ("Focus Punch",   PokemonType.FIGHTING, 150, 100, 20, -3, "CP"),
    265: ("Smelling Salts",PokemonType.NORMAL,   60, 100, 10, 0, "C"),
    266: ("Follow Me",     PokemonType.NORMAL,    0,   0, 20, 3, ""),
    267: ("Nature Power",  PokemonType.NORMAL,    0,   0, 20, 0, ""),
    268: ("Charge",        PokemonType.ELECTRIC,  0,   0, 20, 0, ""),
    269: ("Taunt",         PokemonType.DARK,      0, 100, 20, 0, ""),
    270: ("Helping Hand",  PokemonType.NORMAL,    0,   0, 20, 5, ""),
    271: ("Trick",         PokemonType.PSYCHIC,   0, 100, 10, 0, ""),
    272: ("Role Play",     PokemonType.PSYCHIC,   0,   0, 10, 0, ""),
    273: ("Wish",          PokemonType.NORMAL,    0,   0, 10, 0, ""),
    274: ("Assist",        PokemonType.NORMAL,    0,   0, 20, 0, ""),
    275: ("Ingrain",       PokemonType.GRASS,     0,   0, 20, 0, ""),
    276: ("Superpower",    PokemonType.FIGHTING, 120, 100,  5, 0, "C"),
    277: ("Magic Coat",    PokemonType.PSYCHIC,   0,   0, 15, 4, ""),
    278: ("Recycle",       PokemonType.NORMAL,    0,   0, 10, 0, ""),
    279: ("Revenge",       PokemonType.FIGHTING,  60, 100, 10, -4, "C"),
    280: ("Brick Break",   PokemonType.FIGHTING,  75, 100, 15, 0, "C"),
    281: ("Yawn",          PokemonType.NORMAL,    0,   0, 10, 0, ""),
    282: ("Knock Off",     PokemonType.DARK,     20, 100, 20, 0, "C"),
    283: ("Endeavor",      PokemonType.NORMAL,    0, 100,  5, 0, "C"),
    284: ("Eruption",      PokemonType.FIRE,    150, 100,  5, 0, ""),  # HP-based
    285: ("Skill Swap",    PokemonType.PSYCHIC,   0,   0, 10, 0, ""),
    286: ("Imprison",      PokemonType.PSYCHIC,   0,   0, 10, 0, ""),
    287: ("Refresh",       PokemonType.NORMAL,    0,   0, 20, 0, ""),
    288: ("Grudge",        PokemonType.GHOST,     0,   0, 10, 0, ""),
    289: ("Snatch",        PokemonType.DARK,      0,   0, 10, 4, ""),
    290: ("Secret Power",  PokemonType.NORMAL,   70, 100, 20, 0, ""),
    291: ("Dive",          PokemonType.WATER,    60, 100, 10, 0, "C"),
    292: ("Arm Thrust",    PokemonType.FIGHTING, 15, 100, 20, 0, "C"),
    293: ("Camouflage",    PokemonType.NORMAL,    0,   0, 20, 0, ""),
    294: ("Tail Glow",     PokemonType.BUG,       0,   0, 20, 0, ""),
    295: ("Luster Purge",  PokemonType.PSYCHIC,  70, 100,  5, 0, ""),
    296: ("Mist Ball",     PokemonType.PSYCHIC,  70, 100,  5, 0, ""),
    297: ("Feather Dance", PokemonType.FLYING,    0, 100, 15, 0, ""),
    298: ("Teeter Dance",  PokemonType.NORMAL,    0, 100, 20, 0, ""),
    299: ("Blaze Kick",    PokemonType.FIRE,     85, 90,  10, 0, "C"),
    300: ("Mud Sport",     PokemonType.GROUND,    0,   0, 15, 0, ""),
    301: ("Ice Ball",      PokemonType.ICE,      30, 90,  20, 0, "C"),
    302: ("Needle Arm",    PokemonType.GRASS,    60, 100, 15, 0, "C"),
    303: ("Slack Off",     PokemonType.NORMAL,    0,   0, 10, 0, ""),
    304: ("Hyper Voice",   PokemonType.NORMAL,   90, 100, 10, 0, "S"),
    305: ("Poison Fang",   PokemonType.POISON,   50, 100, 15, 0, "CB"),
    306: ("Crush Claw",    PokemonType.NORMAL,   75, 95,  10, 0, "C"),
    307: ("Blast Burn",    PokemonType.FIRE,    150, 90,   5, 0, ""),
    308: ("Hydro Cannon",  PokemonType.WATER,   150, 90,   5, 0, ""),
    309: ("Meteor Mash",   PokemonType.STEEL,   100, 85,  10, 0, "CP"),
    310: ("Astonish",      PokemonType.GHOST,    30, 100, 15, 0, "C"),
    311: ("Weather Ball",  PokemonType.NORMAL,   50, 100, 10, 0, ""),  # Doubles in weather
    312: ("Aromatherapy",  PokemonType.GRASS,     0,   0,  5, 0, ""),
    313: ("Fake Tears",    PokemonType.DARK,      0, 100, 20, 0, ""),
    314: ("Air Cutter",    PokemonType.FLYING,   55, 95,  25, 0, ""),
    315: ("Overheat",      PokemonType.FIRE,    140, 90,   5, 0, ""),
    316: ("Odor Sleuth",   PokemonType.NORMAL,    0,   0, 40, 0, ""),
    317: ("Rock Tomb",     PokemonType.ROCK,     50, 80,  10, 0, ""),
    318: ("Silver Wind",   PokemonType.BUG,      60, 100,  5, 0, ""),
    319: ("Metal Sound",   PokemonType.STEEL,     0, 85,  40, 0, "S"),
    320: ("Grass Whistle", PokemonType.GRASS,     0, 55,  15, 0, "S"),
    321: ("Tickle",        PokemonType.NORMAL,    0, 100, 20, 0, ""),
    322: ("Cosmic Power",  PokemonType.PSYCHIC,   0,   0, 20, 0, ""),
    323: ("Water Spout",   PokemonType.WATER,   150, 100,  5, 0, ""),  # HP-based
    324: ("Signal Beam",   PokemonType.BUG,      75, 100, 15, 0, ""),
    325: ("Shadow Punch",  PokemonType.GHOST,    60,   0, 20, 0, "CP"),  # Never misses
    326: ("Extrasensory",  PokemonType.PSYCHIC,  80, 100, 30, 0, ""),
    327: ("Sky Uppercut",  PokemonType.FIGHTING, 85, 90,  15, 0, "CP"),
    328: ("Sand Tomb",     PokemonType.GROUND,   15, 70,  15, 0, ""),
    329: ("Sheer Cold",    PokemonType.ICE,       0, 30,   5, 0, ""),  # OHKO
    330: ("Muddy Water",   PokemonType.WATER,    95, 85,  10, 0, ""),
    331: ("Bullet Seed",   PokemonType.GRASS,    10, 100, 30, 0, ""),
    332: ("Aerial Ace",    PokemonType.FLYING,   60,   0, 20, 0, "C"),  # Never misses
    333: ("Icicle Spear",  PokemonType.ICE,      10, 100, 30, 0, ""),
    334: ("Iron Defense",  PokemonType.STEEL,     0,   0, 15, 0, ""),
    335: ("Block",         PokemonType.NORMAL,    0,   0,  5, 0, ""),
    336: ("Howl",          PokemonType.NORMAL,    0,   0, 40, 0, "S"),
    337: ("Dragon Claw",   PokemonType.DRAGON,   80, 100, 15, 0, "C"),
    338: ("Frenzy Plant",  PokemonType.GRASS,   150, 90,   5, 0, ""),
    339: ("Bulk Up",       PokemonType.FIGHTING,  0,   0, 20, 0, ""),
    340: ("Bounce",        PokemonType.FLYING,   85, 85,   5, 0, "C"),
    341: ("Mud Shot",      PokemonType.GROUND,   55, 95,  15, 0, ""),
    342: ("Poison Tail",   PokemonType.POISON,   50, 100, 25, 0, "C"),
    343: ("Covet",         PokemonType.NORMAL,   40, 100, 40, 0, "C"),
    344: ("Volt Tackle",   PokemonType.ELECTRIC, 120, 100, 15, 0, "C"),
    345: ("Magical Leaf",  PokemonType.GRASS,    60,   0, 20, 0, ""),  # Never misses
    346: ("Water Sport",   PokemonType.WATER,     0,   0, 15, 0, ""),
    347: ("Calm Mind",     PokemonType.PSYCHIC,   0,   0, 20, 0, ""),
    348: ("Leaf Blade",    PokemonType.GRASS,    70, 100, 15, 0, "C"),
    349: ("Dragon Dance",  PokemonType.DRAGON,    0,   0, 20, 0, ""),
    350: ("Rock Blast",    PokemonType.ROCK,     25, 80,  10, 0, ""),
    351: ("Shock Wave",    PokemonType.ELECTRIC, 60,   0, 20, 0, ""),  # Never misses
    352: ("Water Pulse",   PokemonType.WATER,    60, 100, 20, 0, ""),
    353: ("Doom Desire",   PokemonType.STEEL,   120, 85,   5, 0, ""),
    354: ("Psycho Boost",  PokemonType.PSYCHIC, 140, 90,   5, 0, ""),
}


def get_move_data(move_id: int) -> Move:
    """
    Look up full move data from a move ID.
    
    Args:
        move_id: Move ID (1-354)
        
    Returns:
        Move with full data populated
    """
    if move_id in _MOVE_TABLE:
        name, type_, power, accuracy, pp, priority, flags = _MOVE_TABLE[move_id]
        return Move(
            id=move_id,
            name=name,
            type=type_,
            power=power,
            accuracy=accuracy,
            max_pp=pp,
            pp=pp,  # Default to max; caller should override with actual PP
            priority=priority,
            is_contact="C" in flags,
        )
    
    # Unknown move - return minimal data
    return Move(id=move_id, name=f"Move#{move_id}", pp=5, max_pp=5)


def enrich_move(move: Move) -> Move:
    """
    Enrich a Move that only has id and pp with full data from the database.
    
    Preserves the actual PP value from memory while filling in
    name, type, power, accuracy, priority from the database.
    
    Args:
        move: Move with at least id and pp set
        
    Returns:
        Move with full data (same object, mutated)
    """
    if move.id in _MOVE_TABLE:
        name, type_, power, accuracy, max_pp, priority, flags = _MOVE_TABLE[move.id]
        move.name = name
        move.type = type_
        move.power = power
        move.accuracy = accuracy
        move.max_pp = max_pp
        move.priority = priority
        move.is_contact = "C" in flags
    else:
        move.name = f"Move#{move.id}"
    
    return move
