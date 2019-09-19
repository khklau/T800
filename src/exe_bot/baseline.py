import sc2
from sc2 import run_game, maps, Race, Difficulty
from sc2.player import Bot, Computer

from strategy.protoss.cannon_rush import CannonRush
from strategy.protoss.voidray_swarm import VoidRaySwarm

from datetime import datetime


# TODO the strategy selection heuristic should be based on historical
# results against this particular opponent
basename = datetime.now().strftime('baseline-%Y%m%dT%H%M%S')
replay_filename = basename + '.SC2Replay'
with open(basename + '.log', 'w') as handle:
    run_game(
            maps.get("AbyssalReefLE"),
            [
                Bot(Race.Protoss, VoidRaySwarm(handle)),
                Computer(Race.Zerg, Difficulty.Hard)
            ],
            realtime=False,
            save_replay_as=replay_filename)
