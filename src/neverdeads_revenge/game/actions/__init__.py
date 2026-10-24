"""Player actions and the AI that answers them, split by what they do."""

from __future__ import annotations

from .core import (
    EMBER_HEAL,
    MIRROR_REFLECTION,
    COUNTS_FAVOUR_EVERY,
    SECOND_MOUTH_BASE,
    Action,
    _ACTION_DIRECTIONS,
    ActionResult,
    FIRST_BLOW,
    COWARD_EDGE,
    LEDGER_CAP,
    KINDLY_PRICE,
    COIN_SCALE,
    LONG_REACH,
    STEP_BEHIND_EVERY,
    SLOW_KNITTING_EVERY,
    HOLLOW_ROAD_COST,
    MOMENTUM_MAX,
    LAST_BREATH_EVASION,
    HUNGRY_ROAD_DAMAGE,
    HUNGRY_ROAD_TRAIL,
    STACK_LIMIT,
    NOTHING_WASTED_DAMAGE,
    ENEMY_BITE,
    MAX_ENEMY_ACTIONS_PER_PLAYER_TURN,
    second_mouth_cap,
    _the,
    _outcome,
)

from .life import (
    tick_statuses,
    inflict,
    _weapon_rule_bonus,
    pay_the_kindly_one,
    _thorns_of,
    _inflicts_of,
    _remove_corpse,
    _one_death_answers,
    _kill_message,
    _on_death,
    _learn,
    _hunter_spoils,
    _drop_coins,
    _scatter_coins,
    _player_takes_damage,
    _maybe_cursed,
    _enemy_takes_damage,
)

from .movement import (
    _try_move,
    _after_step,
    _lay_trail,
    _spring_the_trail,
    _through_stone,
    _collect_coin,
    _knit,
    _bleed,
)

from .combat import (
    resolve_player_attack,
    _knock_back,
    _resolve_attack_on_fortress,
    resolve_enemy_attack,
)

from .turn import (
    take_turn,
    _move_towards_player,
    _hunter_step,
    advance_world,
    _advance_atritas,
    _advance_fortress,
    _melt_fortress,
    _shadow_prey,
    _nearest_enemy,
    _place_beside,
)

from .world import (
    _interact,
    chest_prompt,
    _talk,
    spring_prompt,
    _spring,
    _cleanse,
    _the_lid_bites,
    _open_chest,
    _snapshot,
    _restore,
    _rewind,
)

from .ultimates import (
    ultimate_refusal,
    _ultimate,
    _summon_void,
    _build_fortress,
    _shatter_bell,
    _ravaging_fire,
    _spend_the_turn,
    _is_outer_wall,
    _ultimate_spot,
    _take_fame,
)

from .pack import (
    _pick_up,
    _set_down,
    _equip,
    _inventory,
    _quaff,
    _swallow,
    _after_a_draught,
    _shatter,
    _wake_something,
    _try_descend,
    descend,
    drink,
    drop,
)

from .take import (
    perform_action,
)

__all__ = ["Action", "ActionResult", "perform_action", "take_turn", "advance_world", "descend", "drink", "drop", "MAX_ENEMY_ACTIONS_PER_PLAYER_TURN", "resolve_player_attack", "resolve_enemy_attack", "ultimate_refusal", "inflict", "tick_statuses"]
