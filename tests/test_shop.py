"""Tests for the shop.

Two halves, and they are tested together because they are one feature: the
catalogue (what is on sale, for how much, and what the shop refuses) and the
loadout (what a bought thing actually does once the run starts). A price list
that sells a weapon which does nothing is worse than no shop at all.
"""

from __future__ import annotations

import pytest

from neverdeads_revenge.core.rng import Rng
from neverdeads_revenge.game.actors import NOXX, YETI
from neverdeads_revenge.game.curses import CURSES
from neverdeads_revenge.game.actions import take_turn
from neverdeads_revenge.game.shop import (
    GEAR,
    META_UPGRADES,
    SECTIONS,
    SUPPLIES,
    WILD_OFFERS,
    WILD_SLOTS,
    Loadout,
    ShopError,
    build_stock,
    buy,
    describe_item,
    loadout_from,
    roll_wild_stock,
)
from neverdeads_revenge.game.state import start_run
from neverdeads_revenge.persistence import MetaProgress
from neverdeads_revenge.world.items import ITEMS


def shop(gold: int = 0, **wilds) -> MetaProgress:
    """A progress with coin in it and a shelf to look at."""
    progress = MetaProgress(gold=gold)
    progress.reroll_wilds(Rng(11))
    return progress


def offer_for(progress: MetaProgress, key: str):
    for offer in build_stock(progress):
        if offer.key == key:
            return offer
    raise AssertionError(f"nothing on the shelf called {key!r}")


# -- the catalogue ----------------------------------------------------------
def test_every_shelf_is_on_the_shelf_in_order():
    """The screen draws sections in the order it is given them."""
    stock = build_stock(shop(0))
    seen: list[str] = []
    for offer in stock:
        if offer.section not in seen:
            seen.append(offer.section)
    assert seen == list(SECTIONS)


def test_the_fixed_stock_is_always_there():
    """Supplies, gear and upgrades do not rotate. Only the wilds do."""
    stock = {offer.key for offer in build_stock(shop(0))}
    for item in (*SUPPLIES, *GEAR):
        assert item.key in stock
    for key, upgrade in META_UPGRADES.items():
        if not upgrade.wild:
            assert key in stock, key


def test_a_wild_upgrade_is_not_in_the_fixed_stock():
    """Blood bargain is permanent, but it is not on the sensible shelf."""
    stock = {offer.key for offer in build_stock(shop(0))}
    assert "blood_deal" not in stock
    assert "blood_deal" in {offer.key for offer in build_stock(_with_wilds("blood_deal"))}


def test_prices_are_positive():
    for offer in build_stock(shop(0)):
        assert offer.price > 0, offer.key


def test_what_is_affordable_is_marked_before_the_screen_draws():
    # Read off the catalogue: prices are tuned against the bots, and a test that
    # writes them down a second time fails every time they move.
    cheapest = min(item.price for item in (*SUPPLIES, *GEAR))
    dearest = max(item.price for item in (*SUPPLIES, *GEAR))
    progress = shop(cheapest)

    assert offer_for(progress, "potion").affordable
    assert not offer_for(progress, "bite").affordable, f"{dearest} coins on {cheapest}"


def test_an_item_describes_itself():
    assert describe_item(ITEMS["potion"]) == "heals 8"
    assert "damage" in describe_item(ITEMS["tooth"])
    assert "armour" in describe_item(ITEMS["hide"])


def test_every_wild_offer_is_a_deal_with_two_halves():
    """A bargain whose cost is not stated is not a bargain, it is a trap."""
    for key, offer in WILD_OFFERS.items():
        assert offer.pitch, key
        assert offer.catch, key
        assert offer.price > 0, key


def test_a_permanent_wild_points_at_a_real_upgrade():
    for key, offer in WILD_OFFERS.items():
        if offer.permanent is not None:
            assert offer.permanent in META_UPGRADES, key


def _with_wilds(*keys: str) -> MetaProgress:
    progress = MetaProgress(gold=0)
    progress.wild_stock = list(keys)
    return progress


def test_the_shelf_turns_over_two_at_a_time():
    for seed in range(20):
        stock = roll_wild_stock(Rng(seed))
        assert len(stock) == WILD_SLOTS
        assert len(set(stock)) == WILD_SLOTS, "the same offer twice is one offer"
        assert all(key in WILD_OFFERS for key in stock)


# -- buying -----------------------------------------------------------------
def test_buying_a_draught_sets_it_aside_for_the_next_run():
    price = SUPPLIES[0].price
    progress = shop(price * 3)
    message = buy(progress, offer_for(progress, "potion"))

    assert progress.gold == price * 3 - price
    assert progress.pending == ["potion"]
    assert "potion" in message


def test_buying_gear_sets_it_aside_too():
    progress = shop(1000)
    buy(progress, offer_for(progress, "bite"))
    assert progress.pending == ["bite"]


def test_buying_an_upgrade_is_permanent_and_stacks():
    price = META_UPGRADES["vigour"].price
    progress = shop(price * 4)
    for _ in range(2):
        buy(progress, offer_for(progress, "vigour"))

    assert progress.upgrades["vigour"] == 2
    # Vigour's ladder climbs now, so the second stack costs more than the
    # first: the gold is what the two steps actually cost.
    ladder = sum(META_UPGRADES["vigour"].price_at(i) for i in range(2))
    assert progress.gold == price * 4 - ladder
    assert progress.pending == [], "an upgrade is not consumed by a run"


def test_an_upgrade_cannot_be_bought_past_its_cap():
    progress = shop(4000)
    cap = META_UPGRADES["lantern"].max_stacks
    for _ in range(cap):
        buy(progress, offer_for(progress, "lantern"))

    spent = progress.gold
    with pytest.raises(ShopError):
        buy(progress, offer_for(progress, "lantern"))
    assert progress.gold == spent, "a refusal must not cost anything"


def test_buying_a_wild_waits_for_the_next_run():
    progress = _with_wilds("second_wind")
    progress.gold = WILD_OFFERS["second_wind"].price * 2
    buy(progress, offer_for(progress, "second_wind"))

    assert progress.wilds == ["second_wind"]
    assert progress.gold == WILD_OFFERS["second_wind"].price


def test_a_permanent_wild_goes_straight_into_the_upgrades():
    """There is nothing to wait for: it changes every run from now on."""
    progress = _with_wilds("blood_deal")
    progress.gold = WILD_OFFERS["blood_deal"].price * 2
    buy(progress, offer_for(progress, "blood_deal"))

    assert progress.upgrades["blood_deal"] == 1
    assert progress.wilds == [], "a permanent offer is not spent by a run"


def test_a_permanent_wild_cannot_be_bought_past_its_cap():
    progress = _with_wilds("blood_deal")
    progress.gold = WILD_OFFERS["blood_deal"].price * 6
    for _ in range(META_UPGRADES["blood_deal"].max_stacks):
        buy(progress, offer_for(progress, "blood_deal"))

    with pytest.raises(ShopError):
        buy(progress, offer_for(progress, "blood_deal"))


def test_the_shop_refuses_what_the_purse_cannot_cover():
    progress = shop(5)
    with pytest.raises(ShopError) as refusal:
        buy(progress, offer_for(progress, "bite"))

    assert "5" in str(refusal.value), "the refusal should say what you have"
    assert progress.gold == 5
    assert progress.pending == []


# -- the loadout ------------------------------------------------------------
def test_the_loadout_is_taken_off_the_books():
    """A draught bought for this run is drunk in this run."""
    progress = shop(0)
    progress.pending = ["potion", "bite"]
    progress.wilds = ["greed"]

    loadout = loadout_from(progress)

    assert loadout.pending == ("potion", "bite")
    assert loadout.wilds == ("greed",)
    assert progress.pending == []
    assert progress.wilds == []
    assert loadout.upgrades == progress.upgrades, "upgrades are never consumed"


# -- what a bought thing does ----------------------------------------------
def test_bought_draughts_are_in_the_pack_at_the_first_step():
    state = start_run(NOXX, seed=3, loadout=Loadout(pending=("potion", "elixir")))
    assert [item.item_id for item in state.inventory] == ["potion", "elixir"]


def test_bought_gear_is_worn_at_the_first_step():
    state = start_run(NOXX, seed=3, loadout=Loadout(pending=("bite", "hide")))
    assert state.player.equipment["weapon"].item_id == "bite"
    assert state.player.equipment["armour"].item_id == "hide"


def test_gear_changes_the_numbers_it_says_it_does():
    plain = start_run(NOXX, seed=3)
    armed = start_run(NOXX, seed=3, loadout=Loadout(pending=("bite", "hide")))

    assert armed.player.damage_range[0] == plain.player.damage_range[0] + 2
    assert armed.player.armor == plain.player.armor + 1


def test_vigour_is_health_you_actually_start_with():
    # Read off the table rather than written down twice: these numbers are
    # tuned against the bots, and a test that hardcodes them fails every time
    # the wall is measured again without saying anything about the game.
    per_stack = META_UPGRADES["vigour"].max_hp
    plain = start_run(NOXX, seed=3)
    tough = start_run(NOXX, seed=3, loadout=Loadout(upgrades={"vigour": 3}))

    assert tough.player.max_hp == plain.player.max_hp + per_stack * 3
    assert tough.player.hp == tough.player.max_hp, "bought health you do not have"


def test_haste_and_lantern_do_what_they_say():
    per_stack = META_UPGRADES["haste"].speed
    plain = start_run(NOXX, seed=3)
    upgraded = start_run(
        NOXX, seed=3, loadout=Loadout(upgrades={"haste": 2, "lantern": 1})
    )

    assert upgraded.player.speed == pytest.approx(
        plain.player.speed + per_stack * 2
    )
    assert upgraded.sight_radius == plain.sight_radius + 1


def test_the_blood_bargain_costs_health_for_good():
    """The one offer that is a permanent subtraction, and it must be permanent."""
    plain = start_run(NOXX, seed=3)
    struck = start_run(NOXX, seed=3, loadout=Loadout(upgrades={"blood_deal": 1}))

    assert struck.player.max_hp == plain.player.max_hp - 4
    assert struck.player.speed == pytest.approx(plain.player.speed + 0.15)
    assert struck.player.hp == struck.player.max_hp


def test_the_blood_bargain_can_never_leave_a_hero_at_nothing():
    """Four at a time against a fragile hero would otherwise reach zero."""
    frail = start_run(YETI, seed=3, loadout=Loadout(upgrades={"blood_deal": 2}))
    assert frail.player.max_hp >= 1
    assert frail.player.hp >= 1


def test_upgrades_are_applied_to_every_hero_the_same_way():
    per_stack = META_UPGRADES["vigour"].max_hp
    for hero in (NOXX, YETI):
        state = start_run(hero, seed=3, loadout=Loadout(upgrades={"vigour": 1}))
        assert state.player.max_hp == hero.stats.max_hp + per_stack, hero.key


def test_the_blind_box_always_hands_something_over():
    for seed in range(12):
        state = start_run(NOXX, seed=seed, loadout=Loadout(wilds=("blind_box",)))
        worn = list(state.player.equipment.values())
        assert state.inventory or worn, f"seed {seed} gave nothing"


def test_the_pact_curses_you_and_pays_better():
    state = start_run(NOXX, seed=3, loadout=Loadout(wilds=("pact",)))

    assert len(state.curses) == 1
    assert state.curses[0].key in CURSES
    assert state.coin_multiplier == pytest.approx(1.5)


def test_greed_doubles_the_coin_and_toughens_the_monsters():
    plain = start_run(NOXX, seed=3)
    greedy = start_run(NOXX, seed=3, loadout=Loadout(wilds=("greed",)))

    assert greedy.coin_multiplier == pytest.approx(2.0)
    assert greedy.enemy_hp_multiplier == pytest.approx(1.2)
    assert greedy.enemies, "the floor should still have monsters on it"
    assert all(
        enemy.max_hp > plain_enemy.max_hp
        for enemy, plain_enemy in zip(greedy.enemies, plain.enemies)
    )


def test_grave_goods_puts_the_heavy_blade_in_your_hands():
    state = start_run(NOXX, seed=3, loadout=Loadout(wilds=("grave_goods",)))
    assert state.player.equipment["weapon"].item_id == "grave"
    assert state.player.speed < NOXX.stats.speed, "and it is heavy"


def test_second_wind_holds_the_first_killing_blow():
    state = start_run(NOXX, seed=3, loadout=Loadout(wilds=("second_wind",)))
    assert state.extra_lives == 1

    state.player.stats.hp = 0
    assert state.die("slain") is False
    assert state.player.alive
    assert state.player.hp == 1
    assert state.run_state.value == "playing"

    # And the second one lands. A bargain that works twice is a bargain that
    # was mis-sold.
    state.player.stats.hp = 0
    assert state.die("slain") is True
    assert state.run_state.value == "dead"


def test_two_second_winds_are_two_lives():
    state = start_run(NOXX, seed=3, loadout=Loadout(wilds=("second_wind",) * 2))
    assert state.extra_lives == 2


def test_the_coin_multiplier_reaches_the_pile_on_the_floor():
    from neverdeads_revenge.game.actors import ENEMIES, make_enemy

    plain = start_run(NOXX, seed=3)
    greedy = start_run(NOXX, seed=3, loadout=Loadout(wilds=("greed",)))

    for state in (plain, greedy):
        enemy = make_enemy(ENEMIES["ghoul"], state.player.position)
        enemy.gold = (10, 10)
        state.enemies = [enemy]
        from neverdeads_revenge.game.actions import _drop_coins

        _drop_coins(state, enemy)

    assert plain.dungeon_map.item_at(plain.player.position).gold == 10
    assert greedy.dungeon_map.item_at(greedy.player.position).gold == 20


def test_a_run_without_a_loadout_is_the_run_it_always_was():
    """The shop must not change a run that bought nothing."""
    plain = start_run(NOXX, seed=3)
    explicit = start_run(NOXX, seed=3, loadout=Loadout())

    assert plain.player.max_hp == explicit.player.max_hp
    assert plain.player.speed == explicit.player.speed
    assert plain.coin_multiplier == 1.0
    assert plain.enemy_hp_multiplier == 1.0
    assert plain.extra_lives == 0
    assert plain.sight_radius == explicit.sight_radius


# -- the wild offers that are not about numbers ------------------------------
def _wearing_wild(key: str, seed: int = 3):
    return start_run(NOXX, seed=seed, loadout=Loadout(wilds=(key,)))


def _one_weak_neighbour(state, hp: int = 1):
    from neverdeads_revenge.game.actors import ENEMIES, make_enemy

    player = state.player
    enemy = make_enemy(
        ENEMIES["ghoul"], (player.position[0] + 1, player.position[1])
    )
    enemy.stats.hp = hp
    state.enemies = [enemy]
    state.turn_queue = type(state.turn_queue)([player, enemy])
    state.refresh_vision()
    return enemy


def _kill_it(state, enemy) -> None:
    from neverdeads_revenge.game.actions import Action, perform_action

    for _ in range(40):
        if not enemy.alive:
            return
        perform_action(state, Action.MOVE_EAST)
    raise AssertionError("the player never landed the killing blow")


def test_the_wager_is_a_coin_and_not_a_metaphor():
    """Half the runs it is the best blade in the game, half the runs it is a
    curse, and the player who buys it has decided they do not mind which."""
    from neverdeads_revenge.world.items import ITEMS

    blades = 0
    curses = 0
    for seed in range(80):
        state = _wearing_wild("wager", seed)
        worn = state.player.equipment.get("weapon")
        if state.curses:
            curses += 1
        else:
            blades += 1
            assert worn is not None and ITEMS[worn.item_id].chest_only

    assert blades and curses, f"{blades} blades, {curses} curses"
    assert 20 < blades < 60, f"the coin is not a coin: {blades}/80"


def test_the_hollow_tooth_takes_drinking_away_and_pays_in_kills():
    from neverdeads_revenge.game.actions import Action, perform_action
    from neverdeads_revenge.world.items import ITEMS, make_item

    state = _wearing_wild("hollow_tooth")
    enemy = _one_weak_neighbour(state)
    state.player.stats.hp = 20
    _kill_it(state, enemy)
    assert state.player.hp == 23, "a kill should feed you three"

    state.inventory.append(make_item(ITEMS["potion"]))
    state.player.stats.hp = 10
    perform_action(state, Action.QUAFF)

    assert state.player.hp == 10, "the draught went down anyway"
    assert state.inventory, "the draught was spent on a refusal"


def test_without_it_a_kill_feeds_you_nothing():
    state = start_run(NOXX, seed=3)
    enemy = _one_weak_neighbour(state)
    state.player.stats.hp = 20
    _kill_it(state, enemy)
    assert state.player.hp == 20


def test_the_pilgrims_toll_charges_for_every_floor():
    from neverdeads_revenge.game.actions import Action, perform_action

    state = _wearing_wild("pilgrims_toll")
    assert state.coin_multiplier == pytest.approx(1.5)
    assert state.toll_per_floor == 5

    state.gold = 100
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)

    assert state.depth == 2
    assert state.gold == 95


def test_the_toll_cannot_take_coin_you_do_not_have():
    """A debt the run cannot pay is not a toll, it is a wall."""
    from neverdeads_revenge.game.actions import Action, perform_action

    state = _wearing_wild("pilgrims_toll")
    state.gold = 2
    state.player.position = state.exit_pos
    perform_action(state, Action.DESCEND)

    assert state.depth == 2, "the toll stopped the descent"
    assert state.gold == 0


def test_the_counts_favour_heals_you_whole_on_the_thirteenth_kill():
    from neverdeads_revenge.game.actions import COUNTS_FAVOUR_EVERY

    state = _wearing_wild("counts_favour")
    state.kills = COUNTS_FAVOUR_EVERY - 1
    enemy = _one_weak_neighbour(state)
    state.player.stats.hp = 4

    _kill_it(state, enemy)

    assert state.kills == COUNTS_FAVOUR_EVERY
    assert state.player.hp == state.player.max_hp


def test_the_counts_favour_does_not_pay_on_any_other_kill():
    state = _wearing_wild("counts_favour")
    enemy = _one_weak_neighbour(state)
    state.player.stats.hp = 4

    _kill_it(state, enemy)

    assert state.player.hp == 4, "it healed on the wrong kill"


def test_the_mirror_of_hunger_puts_something_beside_you_when_you_drink():
    from neverdeads_revenge.game.actions import Action, perform_action
    from neverdeads_revenge.world.items import ITEMS, make_item

    state = _wearing_wild("mirror_of_hunger")
    state.enemies = []
    state.inventory.append(make_item(ITEMS["potion"]))
    state.player.stats.hp = 10

    perform_action(state, Action.QUAFF)

    assert len(state.enemies) == 1, "nothing came"
    enemy = state.enemies[0]
    assert (
        max(
            abs(enemy.position[0] - state.player.position[0]),
            abs(enemy.position[1] - state.player.position[1]),
        )
        == 1
    ), "it did not arrive beside you"
    assert take_turn(state, enemy) or not enemy.alive, "it cannot act"


def test_the_nameless_run_trades_the_score_for_the_coin():
    state = _wearing_wild("nameless_run")
    state.floors_cleared = 4
    state.total_turns = 0

    assert state.coin_multiplier == pytest.approx(2.0)
    assert state.score_multiplier == pytest.approx(0.5)
    assert state.score == round((state.base_score + state.speed_bonus) * 0.5)


def test_every_wild_offer_can_come_round():
    """Twelve of them and two slots: a shelf that never shows one of them is a
    shelf with eleven offers on it."""
    from neverdeads_revenge.game.shop import WILD_OFFERS, roll_wild_stock

    seen: set[str] = set()
    for seed in range(200):
        seen |= set(roll_wild_stock(Rng(seed)))
    assert seen == set(WILD_OFFERS), f"never on the shelf: {set(WILD_OFFERS) - seen}"


def test_a_run_with_no_wilds_has_none_in_force():
    state = start_run(NOXX, seed=3)
    assert state.wilds == set()
    assert not state.draughts_forbidden
    assert state.kill_heal == 0
    assert state.toll_per_floor == 0
    assert state.score_multiplier == 1.0


def test_the_permanent_set_is_a_grind_and_not_a_wall():
    """A run banks 50-115 coin, so the full permanent set is twelve to eighteen
    runs. Cheap enough that every run buys something; expensive enough that the
    wall is what you are buying your way through.

    Both halves are asserted, because a price list fails in two directions and
    only one of them is obvious.
    """
    from neverdeads_revenge.game.shop import AMULETS_FOR_SALE, GEAR, SUPPLIES

    # The ladders climb now, so the price of a set is the sum of its steps.
    def ladder(upgrade) -> int:
        return sum(upgrade.price_at(i) for i in range(upgrade.max_stacks))

    full = sum(
        ladder(upgrade) for upgrade in META_UPGRADES.values() if not upgrade.wild
    )
    # Everything: the five-step ladders and all three bloodlines. About forty
    # good runs -- that is the *everything* price, not the price of a hero
    # that can play.
    assert 4000 <= full <= 8000, f"the permanent set costs {full}"

    # What a new player actually saves for: health, a blade, room, a light.
    core = sum(
        ladder(META_UPGRADES[key])
        for key in ("vigour", "whetstone", "pack", "lantern")
    )
    assert 2000 <= core <= 3500, f"the core set costs {core}"
    assert core <= full

    # And something has to be buyable after a bad run, or the first ten runs are
    # a wall with nothing to spend on.
    cheapest = min(item.price for item in (*SUPPLIES, *GEAR, *AMULETS_FOR_SALE))
    assert cheapest <= 60, f"the cheapest thing costs {cheapest}"


def test_the_wild_offers_are_priced_against_the_run_they_change():
    """A wild is a single run's worth of change, so it has to cost less than a
    permanent one -- and the bargains with a permanent catch cost the most,
    because they are the only ones you keep."""
    from neverdeads_revenge.game.shop import META_UPGRADES

    # The Pack is the deliberate exception: a comfort, not a power, and priced
    # below the single-run wilds on purpose. Every *other* permanent upgrade
    # stays the dearest tier in the game.
    cheapest_upgrade = min(
        upgrade.price
        for key, upgrade in META_UPGRADES.items()
        if not upgrade.wild and key != "pack"
    )
    permanent = [
        offer for offer in WILD_OFFERS.values() if offer.permanent is not None
    ]
    single = [offer for offer in WILD_OFFERS.values() if offer.permanent is None]

    assert single, "every wild is permanent?"
    assert max(o.price for o in single) < cheapest_upgrade
    assert permanent, "no permanent wild offers at all"
    assert max(o.price for o in permanent) >= min(o.price for o in single)


def test_the_mirror_of_hunger_delivers_its_own_pitch():
    """"a draught heals half again as much" is what the 115 coin buy. It used to
    buy only the drinking monster, and the first half of that sentence was
    nothing: heal_scale never read the mirror."""
    from neverdeads_revenge.game.actions import Action, perform_action
    from neverdeads_revenge.world.items import ITEMS, make_item

    state = _wearing_wild("mirror_of_hunger")
    state.enemies = []
    state.inventory.append(make_item(ITEMS["potion"]))
    state.player.stats.hp = 4

    perform_action(state, Action.QUAFF)

    assert state.player.stats.hp == 4 + round(8 * 1.5), (
        f"the mirror promised 12, it paid {state.player.stats.hp - 4}"
    )


def test_the_mirror_and_famine_agree_to_a_number():
    """The two halves cancel, which is the reason the wording can meet at all."""
    from neverdeads_revenge.game.curses import CURSES

    state = _wearing_wild("mirror_of_hunger")
    state.add_curse(CURSES["famine"])

    assert state.heal_scale == 0.5 * 1.5
    assert abs(state.heal_scale - 0.75) < 1e-9


def test_the_pack_shelf_line_gets_dearer_as_it_is_bought():
    """The offer in the shop carries the *next* stack's price, and each stack
    costs more than the last -- the fourth slot is a decision."""
    from neverdeads_revenge.game.shop import META_UPGRADES, build_stock
    from neverdeads_revenge.persistence import MetaProgress

    progress = MetaProgress(gold=100_000)
    prices = []
    for _ in range(META_UPGRADES["pack"].max_stacks):
        offers = {offer.key: offer for offer in build_stock(progress)}
        pack = offers["pack"]
        prices.append(pack.price)
        progress.upgrades["pack"] = progress.upgrades.get("pack", 0) + 1

    assert prices == [100, 150, 200, 250, 300], f"the ladder reads {prices}"

    # and once it is maxed it is offered as taken, not as another slot
    offers = {offer.key: offer for offer in build_stock(progress)}
    assert offers["pack"].maxed, "a maxed pack still sold a slot"
