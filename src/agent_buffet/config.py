from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


CompetitionName = Literal["orbit-wars"]


class StrategyConfig(BaseModel):
    expansion: Literal["low", "medium", "high"] = "medium"
    aggression: Literal["low", "medium", "high"] = "medium"
    defense: Literal["low", "medium", "high"] = "medium"
    comet_usage: Literal["off", "opportunistic", "high"] = "off"
    endgame_swarm: bool = True


class TargetScoringConfig(BaseModel):
    distance_weight: float = 100.0
    production_weight: float = 15.0
    enemy_bonus: float = 10.0
    neutral_bonus: float = 4.0
    ship_cost_weight: float = 0.7
    eta_penalty: float = 2.0
    future_production_weight: float = 0.15


class PhysicsConfig(BaseModel):
    sun_avoidance: bool = True
    sun_radius: float = 13.0
    moving_planet_prediction: bool = True
    comet_prediction: bool = False
    continuous_collision_check: bool = True
    max_prediction_ticks: int = Field(default=60, ge=0, le=300)


class AttackConfig(BaseModel):
    min_attack_ships: int = Field(default=5, ge=1)
    send_fraction: float = Field(default=0.55, gt=0.0, le=1.0)
    cooperative_attacks: bool = True
    coop_planet_cap: int = Field(default=8, ge=1, le=50)
    avoid_duplicate_targeting: bool = True
    avoid_oversending: bool = True
    reserve_ships: int = Field(default=4, ge=0)
    max_attacks_per_turn: int = Field(default=12, ge=1, le=200)


class DefenseConfig(BaseModel):
    detect_incoming_fleets: bool = True
    reinforce_under_attack: bool = True
    reserve_home_planet_ships: int = Field(default=10, ge=0)
    abandon_doomed_planets: bool = False
    threat_horizon: int = Field(default=45, ge=1, le=300)


class TestingConfig(BaseModel):
    turns: int = Field(default=220, ge=20, le=1000)
    seeds: int = Field(default=50, ge=1, le=10000)
    opponents: list[str] = Field(default_factory=lambda: ["random", "starter_sniper", "safe_sniper"])


class SourceNote(BaseModel):
    kind: str
    detail: str


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    competition: CompetitionName = "orbit-wars"
    name: str = "current"
    base_template: str = "advanced_modular"
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    target_scoring: TargetScoringConfig = Field(default_factory=TargetScoringConfig)
    physics: PhysicsConfig = Field(default_factory=PhysicsConfig)
    attacks: AttackConfig = Field(default_factory=AttackConfig)
    defense: DefenseConfig = Field(default_factory=DefenseConfig)
    testing: TestingConfig = Field(default_factory=TestingConfig)
    sources: list[SourceNote] = Field(default_factory=list)

    @field_validator("base_template")
    @classmethod
    def known_template(cls, value: str) -> str:
        known = {"simple_sniper", "advanced_modular", "balanced_modular"}
        if value not in known:
            raise ValueError(f"Unknown template {value!r}. Expected one of: {', '.join(sorted(known))}")
        return value


PRESETS: dict[str, dict[str, Any]] = {
    "starter_sniper": {
        "name": "starter_sniper",
        "base_template": "simple_sniper",
        "strategy": {"expansion": "medium", "aggression": "low", "defense": "low", "endgame_swarm": False},
        "physics": {"sun_avoidance": False, "moving_planet_prediction": False, "max_prediction_ticks": 0},
        "attacks": {"cooperative_attacks": False, "avoid_duplicate_targeting": False, "reserve_ships": 2},
        "defense": {"detect_incoming_fleets": False, "reinforce_under_attack": False},
    },
    "safe_sniper": {
        "name": "safe_sniper",
        "base_template": "advanced_modular",
        "strategy": {"expansion": "medium", "aggression": "low", "defense": "medium", "endgame_swarm": False},
        "target_scoring": {"distance_weight": 120, "production_weight": 10, "enemy_bonus": 4, "eta_penalty": 3},
        "physics": {"sun_avoidance": True, "moving_planet_prediction": True, "max_prediction_ticks": 45},
        "attacks": {"send_fraction": 0.45, "cooperative_attacks": False, "avoid_duplicate_targeting": True, "reserve_ships": 6},
    },
    "balanced_ladder": {
        "name": "balanced_ladder",
        "base_template": "advanced_modular",
        "strategy": {"expansion": "high", "aggression": "medium", "defense": "medium", "endgame_swarm": True},
        "target_scoring": {"distance_weight": 100, "production_weight": 15, "enemy_bonus": 10, "ship_cost_weight": 0.7, "eta_penalty": 2},
        "physics": {"sun_avoidance": True, "moving_planet_prediction": True, "max_prediction_ticks": 60},
        "attacks": {"min_attack_ships": 5, "cooperative_attacks": True, "coop_planet_cap": 8, "avoid_duplicate_targeting": True},
        "defense": {"detect_incoming_fleets": True, "reinforce_under_attack": True},
    },
    "fast_expansion": {
        "name": "fast_expansion",
        "base_template": "advanced_modular",
        "strategy": {"expansion": "high", "aggression": "low", "defense": "low", "endgame_swarm": True},
        "target_scoring": {"distance_weight": 85, "production_weight": 18, "enemy_bonus": 2, "neutral_bonus": 12, "eta_penalty": 1.5},
        "attacks": {"send_fraction": 0.62, "reserve_ships": 3, "cooperative_attacks": True},
    },
    "defensive_turtle": {
        "name": "defensive_turtle",
        "base_template": "advanced_modular",
        "strategy": {"expansion": "low", "aggression": "low", "defense": "high", "endgame_swarm": True},
        "target_scoring": {"distance_weight": 135, "production_weight": 12, "enemy_bonus": 3},
        "attacks": {"send_fraction": 0.35, "reserve_ships": 12, "max_attacks_per_turn": 6},
        "defense": {"reserve_home_planet_ships": 18, "threat_horizon": 70},
    },
    "enemy_raider": {
        "name": "enemy_raider",
        "base_template": "advanced_modular",
        "strategy": {"expansion": "medium", "aggression": "high", "defense": "low", "endgame_swarm": True},
        "target_scoring": {"distance_weight": 95, "production_weight": 10, "enemy_bonus": 24, "ship_cost_weight": 0.6},
        "attacks": {"send_fraction": 0.68, "reserve_ships": 4, "cooperative_attacks": True},
    },
    "experimental_comet": {
        "name": "experimental_comet",
        "base_template": "advanced_modular",
        "strategy": {"expansion": "medium", "aggression": "medium", "defense": "medium", "comet_usage": "opportunistic"},
        "physics": {"sun_avoidance": True, "moving_planet_prediction": True, "comet_prediction": True, "max_prediction_ticks": 80},
    },
    "advanced_from_submission77": {
        "name": "advanced_from_submission77",
        "base_template": "advanced_modular",
        "strategy": {"expansion": "high", "aggression": "medium", "defense": "medium", "endgame_swarm": True},
        "target_scoring": {"distance_weight": 92, "production_weight": 18, "enemy_bonus": 12, "ship_cost_weight": 0.65, "eta_penalty": 1.8},
        "physics": {"sun_avoidance": True, "moving_planet_prediction": True, "continuous_collision_check": True, "max_prediction_ticks": 72},
        "attacks": {"send_fraction": 0.58, "cooperative_attacks": True, "coop_planet_cap": 10, "avoid_oversending": True},
        "defense": {"detect_incoming_fleets": True, "reinforce_under_attack": True, "threat_horizon": 60},
    },
}


def preset_names() -> list[str]:
    return sorted(PRESETS)


def preset_config(name: str) -> AgentConfig:
    if name not in PRESETS:
        raise KeyError(f"Unknown preset {name!r}. Available: {', '.join(preset_names())}")
    data = deepcopy(PRESETS[name])
    data.setdefault("sources", [])
    data["sources"].append({"kind": "preset", "detail": name})
    return AgentConfig.model_validate(data)


def load_config(path: Path) -> AgentConfig:
    raw = yaml.safe_load(path.read_text()) or {}
    return AgentConfig.model_validate(raw)


def save_config(config: AgentConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="json", exclude_none=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
