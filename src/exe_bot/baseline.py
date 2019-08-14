import sc2
from sc2 import run_game, maps, Race, Difficulty
from sc2.player import Bot, Computer
from sc2.constants import NEXUS, PROBE, PYLON, ASSIMILATOR, GATEWAY, CYBERNETICSCORE, STALKER, STARGATE, VOIDRAY

from datetime import datetime
import random
import sys


class T800Bot(sc2.BotAI):
    def __init__(self):
        self.ITER_PER_PHASE = 150

    async def on_step(self, iteration):
        self.iteration = iteration
        await self.distribute_workers()
        await self.build_workers()
        await self.build_pylons()
        await self.build_assimilator()
        await self.expand()
        await self.build_barracks()
        await self.build_army()
        await self.attack()

    async def build_workers(self):
        worker_limit = len(self.units(NEXUS)) * 16
        for nexus in self.units(NEXUS).ready.noqueue:
            if self.can_afford(PROBE) and len(self.units(PROBE)) < worker_limit:
                await self.do(nexus.train(PROBE))

    async def build_pylons(self):
        if ((self.supply_left < 5 or self.supply_used > self.supply_cap)
                and not self.already_pending(PYLON)):
            nexuses = self.units(NEXUS).ready
            if nexuses.exists:
                if self.can_afford(PYLON):
                    await self.build(PYLON, near=nexuses.first)

    async def build_assimilator(self):
        for nexus in self.units(NEXUS).ready:
            geysers = self.state.vespene_geyser.closer_than(15.0, nexus)
            for geyser in geysers:
                if not self.can_afford(ASSIMILATOR):
                    break
                worker = self.select_build_worker(geyser.position)
                if worker is None:
                    break
                elif not self.units(ASSIMILATOR).closer_than(1.0, geyser).exists:
                    await self.do(worker.build(ASSIMILATOR, geyser))

    async def build_barracks(self):
        if self.units(PYLON).ready.exists:
            pylon = self.units(PYLON).ready.random
            if (self.units(CYBERNETICSCORE).ready.exists
                    and len(self.units(STARGATE)) <= (self.iteration / self.ITER_PER_PHASE)
                    and self.can_afford(STARGATE)
                    and not self.already_pending(STARGATE)):
                await self.build(STARGATE, near=pylon)
            elif (self.units(GATEWAY).ready.exists
                    and not self.units(CYBERNETICSCORE)
                    and self.can_afford(CYBERNETICSCORE)
                    and not self.already_pending(CYBERNETICSCORE)):
                await self.build(CYBERNETICSCORE, near=pylon)
            elif (len(self.units(GATEWAY)) <= (self.iteration / self.ITER_PER_PHASE)
                    and self.can_afford(GATEWAY)
                    and not self.already_pending(GATEWAY)):
                await self.build(GATEWAY, near=pylon)

    async def build_army(self):
        for gw in self.units(GATEWAY).ready.noqueue:
            if not self.units(STALKER).amount > self.units(VOIDRAY).amount:
                if self.can_afford(STALKER) and self.supply_left > 0:
                    await self.do(gw.train(STALKER))
        for sg in self.units(STARGATE).ready.noqueue:
            if self.can_afford(VOIDRAY) and self.supply_left > 0:
                await self.do(sg.train(VOIDRAY))

    def find_target(self, state):
        if len(self.known_enemy_units) > 0:
            return random.choice(self.known_enemy_units)
        elif len(self.known_enemy_structures) > 0:
            return random.choice(self.known_enemy_structures)
        else:
            return self.enemy_start_locations[0]

    async def attack(self):
        attacker_config = {
            STALKER: {'attack_size': 15, 'defend_size': 5},
            VOIDRAY: {'attack_size': 8, 'defend_size': 3}
        }

        for unit, config in attacker_config.items():
            if self.units(unit).amount > config['attack_size']:
                for u in self.units(unit).idle:
                    await self.do(u.attack(self.find_target(self.state)))
            elif self.units(unit).amount > config['defend_size']:
                if len(self.known_enemy_units) > 0:
                    for u in self.units(unit).idle:
                        await self.do(u.attack(random.choice(self.known_enemy_units)))

    async def expand(self):
        if self.units(NEXUS).amount < (self.iteration / self.ITER_PER_PHASE) and self.can_afford(NEXUS):
            await self.expand_now()

replay_filename = datetime.now().strftime('baseline-%Y%m%dT%H%M%S.SC2Replay')
run_game(
        maps.get("AbyssalReefLE"),
        [
            Bot(Race.Protoss, T800Bot()),
            Computer(Race.Terran, Difficulty.Hard)
        ],
        realtime=False,
        save_replay_as=replay_filename)
