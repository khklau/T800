import sc2
from sc2 import run_game, maps, Race, Difficulty
from sc2.player import Bot, Computer
from sc2.constants import NEXUS, PROBE, PYLON, ASSIMILATOR, GATEWAY, CYBERNETICSCORE
from sc2.constants import STALKER, STARGATE, VOIDRAY, OBSERVER, ROBOTICSFACILITY
from sc2.position import Point2

from datetime import datetime
import math
import random
import sys


class T800Bot(sc2.BotAI):
    def __init__(self, log):
        self.log = log
        self.ITER_PER_PHASE = 150
        self.NEXUS_LIMIT = 5
        self.PATROL_RADIUS = 10
        self.PATROL_ARC_NUM = 8
        self.BASE_NAMES = ['nexus', 'commandcenter', 'orbitalcommand', 'planetaryfortress', 'hatchery']
        self.assigned_enemy_bases = {}
        self.unassigned_enemy_bases = {}
        self.observer_assignment = {}

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
        unassigned = {}
        active_bases = self.known_enemy_structures.filter(
            lambda building: building.name.lower() in self.BASE_NAMES
        )
        for (observer_tag, base_tag) in self.observer_assignment.items():
            match = active_bases.find_by_tag(base_tag)
            if match is None:
                unassigned[observer_tag] = base_tag
        for (observer_tag, base_tag) in unassigned.items():
            del self.observer_assignment[observer_tag]
            del self.assigned_enemy_bases[base_tag]
        for active in active_bases:
            # TODO: Handle Terran structures that can move
            if active.tag not in self.assigned_enemy_bases.keys():
                self.unassigned_enemy_bases[active.tag] = active.position

    def assign_observer(self, observer):
        if len(self.unassigned_enemy_bases) == 0:
            return
        (base_tag, base_position) = list(self.unassigned_enemy_bases.items())[0]
        self.assigned_enemy_bases[base_tag] = base_position
        self.observer_assignment[observer.tag] = base_tag
        del self.unassigned_enemy_bases[base_tag]

    def audit_observers(self):
        dead_observers = {}
        alive_observers = self.units(OBSERVER)
        for (observer_tag, base_tag) in self.observer_assignment.items():
            match = alive_observers.find_by_tag(observer_tag)
            if match is None:
                dead_observers[observer_tag] = base_tag
        for dead in dead_observers.keys():
            del self.observer_assignment[dead]
        for alive in alive_observers:
            if alive.tag not in self.observer_assignment.keys():
                self.assign_observer(alive)

    def calc_angle(self, target_position, unit_position):
        height = unit_position.y - target_position.y
        width = unit_position.x - target_position.x
        radians = math.atan2(height, width)
        return radians

    def calc_position(self, center, radius, radians):
        map_size = self.game_info.map_size
        y_offset = math.sin(radians) * radius
        x_offset = math.cos(radians) * radius
        x_point = x_offset + center.x
        y_point = y_offset + center.y
        if x_point < 0:
            x_point = 0
        elif x_point >= map_size[0]:
            x_point = map_size[0] - 1
        if y_point < 0:
            y_point = 0
        elif y_point >= map_size[1]:
            y_point = map_size[1] - 1
        position = Point2(tuple([x_point, y_point]))
        return position

    def plan_base_search(self, unit_position):
        return self.enemy_start_locations[0]

    def plan_patrol(self, target_position, unit_position):
        arc = (math.pi * 2.0) / self.PATROL_ARC_NUM
        current_angle = self.calc_angle(target_position, unit_position)
        if current_angle < 0:
            rounded_angle = arc * math.ceil(current_angle / arc)
        else:
            rounded_angle = arc * math.floor(current_angle / arc)
        next_angle = rounded_angle + arc
        patrol_waypoint = self.calc_position(target_position, self.PATROL_RADIUS, next_angle)
        return patrol_waypoint

    async def scout(self):
        self.register_enemy_bases()
        self.audit_observers()
        idle_observers = self.units(OBSERVER).idle
        for ob in idle_observers:
            if ob.tag not in self.observer_assignment:
                # We have more observers than known enemy bases
                print('iteration (%d): observer %d at (%d, %d) searching for enemy bases' % (
                            self.iteration,
                            ob.tag,
                            ob.position.x,
                            ob.position.y),
                            file=self.log)
                enemy_location = self.plan_base_search(ob.position)
            else:
                base_tag = self.observer_assignment[ob.tag]
                assigned_position = self.assigned_enemy_bases[base_tag]
                distance = ob.position.distance_to(assigned_position)
                if distance <= (self.PATROL_RADIUS * 1.05):
                    # start patroling
                    enemy_location = self.plan_patrol(assigned_position, ob.position)
                    print('iteration (%d): observer %d at (%d, %d) patroling base %d at (%d, %d), waypoint (%d, %d)' % (
                            self.iteration,
                            ob.tag,
                            ob.position.x,
                            ob.position.y,
                            base_tag,
                            assigned_position.x,
                            assigned_position.y,
                            enemy_location.x,
                            enemy_location.y),
                            file=self.log)
                else:
                    print('iteration (%d): moving observer %d at (%d, %d) to assigned base %d at (%d, %d)' % (
                            self.iteration,
                            ob.tag,
                            ob.position.x,
                            ob.position.y,
                            base_tag,
                            assigned_position.x,
                            assigned_position.y),
                            file=self.log)
                    enemy_location = assigned_position
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
            if ((self.units(OBSERVER).amount == 0 or len(self.unassigned_enemy_bases) > 0)
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
            print('iteration (%d): unit %d at (%d, %d) - attacking closest enemy unit name = %s, tag = %d, position = (%d, %d)' % (
                    self.iteration,
                    attacker.tag,
                    attacker.position.x,
                    attacker.position.y,
                    target.name,
                    target.tag,
                    target.position.x,
                    target.position.y),
                    file=self.log)
        elif len(self.known_enemy_structures) > 0:
            target = self.known_enemy_structures.closest_to(attacker)
            print('iteration (%d): unit %d at (%d, %d) - attacking closest enemy structure name = %s, tag = %d, position = (%d, %d)' % (
                    self.iteration,
                    attacker.tag,
                    attacker.position.x,
                    attacker.position.y,
                    target.name,
                    target.tag,
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
            VOIDRAY: {'attack_size': 16, 'defend_size': 3}
        }

        for unit, config in attacker_config.items():
            unit_group = self.units(unit)
            idle_units = unit_group.idle
            busy_units = unit_group - idle_units
            busy_count = len(busy_units)
            idle_count = len(idle_units)

            if (idle_count > config['attack_size']
                    or (self.units(NEXUS).amount == 0 and self.units(unit).amount > 0)):
                target = self.find_target(self.state, self.units(unit).first)
                for u in idle_units:
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
                        for u in idle_units:
                            print('iteration (%d): unit %d at (%d, %d) - defending against: name = %s, tag = %d, position = (%d, %d), distance to nexus = %d' % (
                                    self.iteration,
                                    u.tag,
                                    u.position.x,
                                    u.position.y,
                                    closest_enemy.name,
                                    closest_enemy.tag,
                                    closest_enemy.position.x,
                                    closest_enemy.position.y,
                                    distance),
                                    file=self.log)
                            await self.do(u.attack(closest_enemy))
            elif busy_count > 0:
                for u in idle_units:
                    squad_mate = busy_units.closest_to(u)
                    target = squad_mate.order_target
                    if isinstance(target, Point2):
                        print('iteration (%d): unit %d at (%d, %d) - moving with (%d) at (%d, %d) to position at (%d, %d)' % (
                                self.iteration,
                                u.tag,
                                u.position.x,
                                u.position.y,
                                squad_mate.tag,
                                squad_mate.position.x,
                                squad_mate.position.y,
                                target.x,
                                target.y),
                                file=self.log)
                    else:
                        enemy = target
                        target = self.known_enemy_units.find_by_tag(enemy)
                        if target is None:
                            print('iteration (%d): unit %d at (%d, %d) - order target (%d) no longer exists' % (
                                    self.iteration,
                                    u.tag,
                                    u.position.x,
                                    u.position.y,
                                    enemy),
                                    file=self.log)
                            return
                        else:
                            print('iteration (%d): unit %d at (%d, %d) - assisting (%d) at (%d, %d) attack: name = %s, tag = %d, position = (%d, %d)' % (
                                    self.iteration,
                                    u.tag,
                                    u.position.x,
                                    u.position.y,
                                    squad_mate.tag,
                                    squad_mate.position.x,
                                    squad_mate.position.y,
                                    target.name,
                                    target.tag,
                                    target.position.x,
                                    target.position.y),
                                    file=self.log)
                    await self.do(u.attack(target))

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
                Computer(Race.Zerg, Difficulty.Hard)
            ],
            realtime=False,
            save_replay_as=replay_filename)
