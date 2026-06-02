"""Generated Orbit Wars modular agent.

This file is self-contained for Kaggle submission. It receives an observation
and returns moves shaped as: [[from_planet_id, direction_angle, num_ships], ...].
"""

import math


STRATEGY = {'expansion': 'high', 'aggression': 'low', 'defense': 'low', 'comet_usage': 'off', 'endgame_swarm': True}
TARGET = {'distance_weight': 85.0, 'production_weight': 18.0, 'enemy_bonus': 2.0, 'neutral_bonus': 12.0, 'ship_cost_weight': 0.7, 'eta_penalty': 1.5, 'future_production_weight': 0.15}
PHYSICS = {'sun_avoidance': True, 'sun_radius': 13.0, 'moving_planet_prediction': True, 'comet_prediction': False, 'continuous_collision_check': True, 'max_prediction_ticks': 60}
ATTACKS = {'min_attack_ships': 5, 'send_fraction': 0.62, 'cooperative_attacks': True, 'coop_planet_cap': 8, 'avoid_duplicate_targeting': True, 'avoid_oversending': True, 'reserve_ships': 3, 'max_attacks_per_turn': 12}
DEFENSE = {'detect_incoming_fleets': True, 'reinforce_under_attack': True, 'reserve_home_planet_ships': 10, 'abandon_doomed_planets': False, 'threat_horizon': 45}


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _player(obs):
    return int(_get(obs, "player", _get(obs, "player_id", 1)) or 1)


def _step(obs):
    return int(_get(obs, "step", _get(obs, "turn", 0)) or 0)


def _total_steps(obs):
    return int(_get(obs, "total_steps", _get(obs, "episodeSteps", 400)) or 400)


def _normalize_planet(planet, index):
    x = float(_get(planet, "x", 0.0) or 0.0)
    y = float(_get(planet, "y", 0.0) or 0.0)
    angle = float(_get(planet, "angle", math.atan2(y, x)) or 0.0)
    orbit_radius = float(_get(planet, "orbit_radius", _get(planet, "radius", math.hypot(x, y))) or 0.0)
    return {
        "id": int(_get(planet, "id", _get(planet, "planet_id", index)) or index),
        "x": x,
        "y": y,
        "owner": int(_get(planet, "owner", _get(planet, "player", 0)) or 0),
        "ships": int(_get(planet, "ships", _get(planet, "ship_count", 0)) or 0),
        "production": int(_get(planet, "production", _get(planet, "growth", 1)) or 1),
        "angle": angle,
        "orbit_radius": orbit_radius,
        "angular_velocity": float(_get(planet, "angular_velocity", _get(planet, "omega", 0.0)) or 0.0),
    }


def get_planets(obs):
    raw = _get(obs, "planets", []) or []
    if isinstance(raw, dict):
        raw = list(raw.values())
    return [_normalize_planet(planet, index) for index, planet in enumerate(raw)]


def get_fleets(obs):
    raw = _get(obs, "fleets", []) or []
    if isinstance(raw, dict):
        raw = list(raw.values())
    result = []
    for fleet in raw:
        result.append({
            "owner": int(_get(fleet, "owner", _get(fleet, "player", 0)) or 0),
            "source": int(_get(fleet, "source", _get(fleet, "from", -1)) or -1),
            "target": int(_get(fleet, "target", _get(fleet, "to", -1)) or -1),
            "ships": int(_get(fleet, "ships", _get(fleet, "ship_count", 0)) or 0),
            "eta": int(_get(fleet, "eta", _get(fleet, "remaining", 999)) or 999),
        })
    return result


def get_fleet_speed(num_ships):
    return max(1.5, 9.0 / math.sqrt(max(1, int(num_ships))))


def distance(a, b):
    return math.hypot(b["x"] - a["x"], b["y"] - a["y"])


def find_angle_to_planet(source, target, eta=0):
    predicted = predict_planet_position(target, eta)
    return math.atan2(predicted["y"] - source["y"], predicted["x"] - source["x"])


def predict_planet_position(planet, ticks):
    if not PHYSICS.get("moving_planet_prediction"):
        return planet
    ticks = max(0, min(int(ticks), int(PHYSICS.get("max_prediction_ticks", 60))))
    radius = planet.get("orbit_radius") or math.hypot(planet["x"], planet["y"])
    if not radius:
        return planet
    angle = planet.get("angle", math.atan2(planet["y"], planet["x"])) + planet.get("angular_velocity", 0.0) * ticks
    predicted = dict(planet)
    predicted["x"] = math.cos(angle) * radius
    predicted["y"] = math.sin(angle) * radius
    return predicted


def travel_eta(source, target, ships):
    dist = distance(source, target)
    return max(1, int(math.ceil(dist / get_fleet_speed(ships))))


def sun_collision(source, target):
    if not PHYSICS.get("sun_avoidance"):
        return False
    x1, y1 = source["x"], source["y"]
    x2, y2 = target["x"], target["y"]
    dx = x2 - x1
    dy = y2 - y1
    denom = dx * dx + dy * dy
    if denom <= 0:
        return False
    t = max(0.0, min(1.0, -(x1 * dx + y1 * dy) / denom))
    closest_x = x1 + t * dx
    closest_y = y1 + t * dy
    return math.hypot(closest_x, closest_y) <= float(PHYSICS.get("sun_radius", 13.0))


def predict_total_ships(planet, eta, fleets, player):
    total = int(planet["ships"])
    if planet["owner"]:
        total += int(planet["production"]) * max(0, eta)
    for fleet in fleets:
        if fleet.get("target") != planet["id"] or fleet.get("eta", 999) > eta:
            continue
        if fleet.get("owner") == planet["owner"]:
            total += int(fleet.get("ships", 0))
        else:
            total -= int(fleet.get("ships", 0))
    return total


def incoming_enemy_pressure(planet, fleets, player, horizon):
    pressure = 0
    for fleet in fleets:
        if fleet.get("target") == planet["id"] and fleet.get("owner") != player and fleet.get("eta", 999) <= horizon:
            pressure += int(fleet.get("ships", 0))
    return pressure


def get_planets_under_attack(owned, fleets, player):
    horizon = int(DEFENSE.get("threat_horizon", 45))
    threatened = []
    for planet in owned:
        pressure = incoming_enemy_pressure(planet, fleets, player, horizon)
        if pressure > planet["ships"] + planet["production"] * min(horizon, 20):
            threatened.append((planet, pressure))
    return threatened


def target_score(source, target, fleets, player, committed):
    ships_to_send = max(ATTACKS.get("min_attack_ships", 5), target["ships"] + 1 - committed.get(target["id"], 0))
    eta = travel_eta(source, target, max(1, ships_to_send))
    future_ships = predict_total_ships(target, eta, fleets, player)
    owner = target["owner"]
    score = 0.0
    score += target["production"] * float(TARGET.get("production_weight", 15))
    score += float(TARGET.get("distance_weight", 100)) / max(1.0, distance(source, target))
    score -= max(0, future_ships) * float(TARGET.get("ship_cost_weight", 0.7))
    score -= eta * float(TARGET.get("eta_penalty", 2))
    score += max(0, eta * target["production"]) * float(TARGET.get("future_production_weight", 0.15))
    if owner == 0:
        score += float(TARGET.get("neutral_bonus", 4))
        if STRATEGY.get("expansion") == "high":
            score += 8
    elif owner != player:
        score += float(TARGET.get("enemy_bonus", 10))
        if STRATEGY.get("aggression") == "high":
            score += 8
    if sun_collision(source, target) or sun_collision(source, predict_planet_position(target, eta)):
        score -= 100000
    return score, eta, max(0, future_ships)


def plan_reinforcements(owned, fleets, player, moves, spent):
    if not DEFENSE.get("reinforce_under_attack"):
        return
    threatened = get_planets_under_attack(owned, fleets, player)
    donors = sorted(owned, key=lambda p: -p["ships"])
    for target, pressure in threatened:
        need = max(0, pressure + 3 - target["ships"])
        if need <= 0:
            continue
        for donor in donors:
            if donor["id"] == target["id"]:
                continue
            available = donor["ships"] - spent.get(donor["id"], 0) - int(ATTACKS.get("reserve_ships", 4))
            if available <= 0:
                continue
            ships = min(available, need)
            if ships >= 2:
                eta = travel_eta(donor, target, ships)
                predicted_target = predict_planet_position(target, eta)
                if not sun_collision(donor, target) and not sun_collision(donor, predicted_target):
                    moves.append([donor["id"], find_angle_to_planet(donor, target, eta), int(ships)])
                    spent[donor["id"]] = spent.get(donor["id"], 0) + int(ships)
                    need -= ships
            if need <= 0:
                break


def plan_coop_attack(source, target, owned, fleets, player, committed, moves, spent):
    if not ATTACKS.get("cooperative_attacks"):
        return False
    candidate_donors = sorted(owned, key=lambda p: distance(p, target))[: int(ATTACKS.get("coop_planet_cap", 8))]
    projected = committed.get(target["id"], 0)
    planned = []
    for donor in candidate_donors:
        available = donor["ships"] - spent.get(donor["id"], 0) - int(ATTACKS.get("reserve_ships", 4))
        if available < int(ATTACKS.get("min_attack_ships", 5)):
            continue
        eta = travel_eta(donor, target, max(1, int(available * ATTACKS.get("send_fraction", 0.55))))
        needed = max(0, predict_total_ships(target, eta, fleets, player) + 2 - projected)
        ships = min(int(available * ATTACKS.get("send_fraction", 0.55)), needed)
        if (
            ships >= int(ATTACKS.get("min_attack_ships", 5))
            and not sun_collision(donor, target)
            and not sun_collision(donor, predict_planet_position(target, eta))
        ):
            planned.append([donor["id"], find_angle_to_planet(donor, target, eta), int(ships)])
            projected += ships
        if projected > predict_total_ships(target, eta, fleets, player) + 2:
            break
    if len(planned) <= 1:
        return False
    for move in planned:
        moves.append(move)
        spent[move[0]] = spent.get(move[0], 0) + move[2]
        committed[target["id"]] = committed.get(target["id"], 0) + move[2]
    return True


def _endgame(step, total_steps):
    return STRATEGY.get("endgame_swarm") and step >= max(0, total_steps - 100)


def agent(obs):
    player = _player(obs)
    planets = get_planets(obs)
    fleets = get_fleets(obs)
    step = _step(obs)
    total_steps = _total_steps(obs)
    owned = [p for p in planets if p["owner"] == player]
    targets = [p for p in planets if p["owner"] != player]
    moves = []
    spent = {}
    committed = {}

    if not owned or not targets:
        return moves

    if DEFENSE.get("detect_incoming_fleets"):
        plan_reinforcements(owned, fleets, player, moves, spent)

    max_attacks = int(ATTACKS.get("max_attacks_per_turn", 12))
    if _endgame(step, total_steps):
        reserve = 1
        send_fraction = 0.92
    else:
        reserve = int(ATTACKS.get("reserve_ships", 4))
        if STRATEGY.get("defense") == "high":
            reserve += int(DEFENSE.get("reserve_home_planet_ships", 10))
        send_fraction = float(ATTACKS.get("send_fraction", 0.55))

    for source in sorted(owned, key=lambda p: -p["ships"]):
        if len(moves) >= max_attacks:
            break
        available = source["ships"] - spent.get(source["id"], 0) - reserve
        if available < int(ATTACKS.get("min_attack_ships", 5)):
            continue

        scored = []
        for target in targets:
            if ATTACKS.get("avoid_duplicate_targeting") and committed.get(target["id"], 0) > target["ships"] + 5:
                continue
            score, eta, future_ships = target_score(source, target, fleets, player, committed)
            scored.append((score, eta, future_ships, target))
        if not scored:
            continue
        scored.sort(key=lambda item: item[0], reverse=True)
        _, eta, future_ships, target = scored[0]
        needed = max(int(ATTACKS.get("min_attack_ships", 5)), int(future_ships + 2 - committed.get(target["id"], 0)))
        ships = min(int(available * send_fraction), needed)

        if ships < int(ATTACKS.get("min_attack_ships", 5)):
            continue
        predicted_target = predict_planet_position(target, eta)
        if sun_collision(source, target) or sun_collision(source, predicted_target):
            continue
        if ATTACKS.get("cooperative_attacks") and needed > available:
            if plan_coop_attack(source, target, owned, fleets, player, committed, moves, spent):
                continue
        moves.append([source["id"], find_angle_to_planet(source, target, eta), int(ships)])
        spent[source["id"]] = spent.get(source["id"], 0) + int(ships)
        committed[target["id"]] = committed.get(target["id"], 0) + int(ships)

    return moves[:max_attacks]