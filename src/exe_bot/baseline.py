import sc2
from sc2 import run_game, maps, Race, Difficulty
from sc2.player import Bot, Computer
from sc2.constants import NEXUS, PROBE, PYLON, ASSIMILATOR, GATEWAY, CYBERNETICSCORE
from sc2.constants import STALKER, STARGATE, VOIDRAY, OBSERVER, ROBOTICSFACILITY

from datetime import datetime
import random
import sys


class T800Bot(sc2.BotAI):
    def __init__(self, log):
        self.log = log
        self.ITER_PER_PHASE = 150
        self.NEXUS_LIMIT = 5
        self.BASE_NAMES = ['nexus', 'commandcenter', 'orbitalcommand', 'planetaryfortress', 'hatchery']
        self.enemy_base_locations = {}
        self.observer_locations = {}

    async def on_step(self, iteration):
        self.iteration = iteration
        await self.scout()
        await self.distribute_workers()
        await self.build_workers()
        await self.build_pylons()
        await self.build_assimilator()
        await self.expand()
        await self.build_barracks()
        await self.build_army()
        await self.attack()

    def register_enemy_bases(self):
        active_bases = [building.position
                for building in self.known_enemy_structures
                if building.name.lower() in self.BASE_NAMES]
        inactive_bases = []
        for location in self.enemy_base_locations.keys():
            if location not in active_bases:
                inactive_bases.append(location)
        for inactive in inactive_bases:
            del self.enemy_base_locations[inactive]
        for active in active_bases:
            if active not in self.enemy_base_locations:
                self.enemy_base_locations[active] = self.iteration

    def assign_observer(self, observer):
        pass

    def audit_observers(self):
        alive_observers = sorted(ob.tag for ob in self.units(OBSERVER))
        dead_observers = []
        for observer in self.observer_locations.keys():
            if observer not in alive_observers:
                dead_observers.append(observer)
        for observer in dead_observers:
            del self.observer_locations[observer]
        for alive in alive_observers:
            if alive not in self.observer_locations:
                self.assign_observer(alive)

    async def scout(self):
        self.register_enemy_bases()
        self.audit_observers()
        if len(self.units(OBSERVER)) == 0:
            return
        for ob in self.units(OBSERVER).idle:
            if len(self.enemy_base_locations) == 0:
                enemy_location = self.enemy_start_locations[0]
            else:
                enemy_location = list(self.enemy_base_locations)[0]
            await self.do(ob.move(enemy_location))

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
                    and len(self.units(ROBOTICSFACILITY)) < 1
                    and self.can_afford(ROBOTICSFACILITY)
                    and not self.already_pending(ROBOTICSFACILITY)):
                await self.build(ROBOTICSFACILITY, near=pylon)
            elif (self.units(CYBERNETICSCORE).ready.exists
                    and len(self.units(STARGATE)) <= (self.iteration / self.ITER_PER_PHASE)
                    and self.can_afford(STARGATE)
                    and not self.already_pending(STARGATE)):
                await self.build(STARGATE, near=pylon)
            elif (self.units(GATEWAY).ready.exists
                    and not self.units(CYBERNETICSCORE)
                    and self.can_afford(CYBERNETICSCORE)
                    and not self.already_pending(CYBERNETICSCORE)):
                await self.build(CYBERNETICSCORE, near=pylon)
            elif (len(self.units(GATEWAY)) < 1
                    and self.can_afford(GATEWAY)
                    and not self.already_pending(GATEWAY)):
                await self.build(GATEWAY, near=pylon)

    async def build_army(self):
        for rf in self.units(ROBOTICSFACILITY).ready.noqueue:
            if (self.units(OBSERVER).amount == 0
                    and self.can_afford(OBSERVER)
                    and self.supply_left > 0):
                await self.do(rf.train(OBSERVER))
        for sg in self.units(STARGATE).ready.noqueue:
            if self.can_afford(VOIDRAY) and self.supply_left > 0:
                await self.do(sg.train(VOIDRAY))

    def find_target(self, state, attacker):
        target = None
        enemy_army = self.known_enemy_units.not_structure
        if len(enemy_army) > 0:
            target = enemy_army.closest_to(attacker)
            print('iteration (%d): unit %d at (%d, %d) - attacking closest enemy unit %s at position at (%d, %d)' % (
                    self.iteration,
                    attacker.tag,
                    attacker.position.x,
                    attacker.position.y,
                    target.name,
                    target.position.x,
                    target.position.y),
                    file=self.log)
        elif len(self.known_enemy_structures) > 0:
            target = self.known_enemy_structures.closest_to(attacker)
            print('iteration (%d): unit %d at (%d, %d) - attacking closest enemy structure %s at position at (%d, %d)' % (
                    self.iteration,
                    attacker.tag,
                    attacker.position.x,
                    attacker.position.y,
                    target.name,
                    target.position.x,
                    target.position.y),
                    file=self.log)
        else:
            target = self.enemy_start_locations[0]
            print('iteration (%d): unit %d at (%d, %d) - attacking default enemy start position at (%d, %d)' % (
                    self.iteration,
                    attacker.tag,
                    attacker.position.x,
                    attacker.position.y,
                    target.x,
                    target.y),
                    file=self.log)
        return target

    async def attack(self):
        attacker_config = {
            STALKER: {'attack_size': 15, 'defend_size': 5},
            VOIDRAY: {'attack_size': 16, 'defend_size': 2}
        }

        for unit, config in attacker_config.items():
            idle_count = len(self.units(unit).idle)
            if (idle_count > config['attack_size']
                    or (self.units(NEXUS).amount == 0 and self.units(unit).amount > 0)):
                target = self.find_target(self.state, self.units(unit).first)
                for u in self.units(unit).idle:
                    await self.do(u.attack(target))
            elif idle_count > config['defend_size']:
                main_nexus = self.units(NEXUS).first
                if len(self.known_enemy_units) > 0:
                    enemy_by_distance = sorted(
                            self.known_enemy_units,
                            key=lambda enemy: enemy.position.distance_to(main_nexus.position))
                    closest_enemy = enemy_by_distance[0]
                    distance = main_nexus.position.distance_to(closest_enemy.position)
                    if distance <= 50:
                        for u in self.units(unit).idle:
                            print('iteration (%d): unit %d at (%d, %d) - defending against: name = %s, position = (%d, %d), distance to nexus = %d' % (
                                    self.iteration,
                                    u.tag,
                                    u.position.x,
                                    u.position.y,
                                    closest_enemy.name,
                                    closest_enemy.position.x,
                                    closest_enemy.position.y,
                                    distance),
                                    file=self.log)
                            await self.do(u.attack(closest_enemy))
            else:
                busy_count = len(self.units(unit)) - idle_count
                if busy_count > idle_count:
                    print('iteration (%d): busy units = %d, idle units = %d' % (
                            self.iteration,
                            busy_count,
                            idle_count),
                            file=self.log)

    async def expand(self):
        if (self.units(NEXUS).amount < (self.iteration / (self.ITER_PER_PHASE * 2))
                and self.units(NEXUS).amount < self.NEXUS_LIMIT
                and self.can_afford(NEXUS)
                and not self.already_pending(NEXUS)):
            await self.expand_now()

basename = datetime.now().strftime('baseline-%Y%m%dT%H%M%S')
replay_filename = basename + '.SC2Replay'
with open(basename + '.log', 'w') as handle:
    run_game(
            maps.get("AbyssalReefLE"),
            [
                Bot(Race.Protoss, T800Bot(handle)),
                Computer(Race.Terran, Difficulty.Hard)
            ],
            realtime=False,
            save_replay_as=replay_filename)
