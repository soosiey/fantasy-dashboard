from fantasy_dashboard.draft import build_draft_result_rows
from fantasy_dashboard.models.draft import DraftPickContainer, DraftPickModel


# Sleeper auction metadata should produce an ordered, typed draft-pick model.
def test_draft_pick_container_parses_auction_amounts() -> None:
    draft = DraftPickContainer.from_api(
        [
            {
                "pick_no": 2,
                "player_id": "player-2",
                "picked_by": "user-2",
                "metadata": {
                    "first_name": "CeeDee",
                    "last_name": "Lamb",
                    "amount": "31",
                },
            },
            {
                "pick_no": 1,
                "player_id": "player-1",
                "metadata": {
                    "first_name": "Ja'Marr",
                    "last_name": "Chase",
                },
            },
        ]
    )

    assert [pick.pick_number for pick in draft.picks] == [1, 2]
    assert draft.picks[0].amount is None
    assert draft.picks[1].amount == 31.0
    assert draft.picks[1].picked_by == "user-2"


# Search should use catalog names while retaining metadata when a player is absent.
def test_build_draft_result_rows_filters_player_names() -> None:
    picks = [
        DraftPickModel(1, "player-1", "Old Name", 25.0),
        DraftPickModel(2, "player-2", "Metadata Player", None),
    ]
    players = {
        "player-1": {"first_name": "Justin", "last_name": "Jefferson"},
    }

    rows = build_draft_result_rows(
        picks,
        players,
        {"": "Draft User"},
        "  JEFFER  ",
    )

    assert len(rows) == 1
    assert rows[0].player_name == "Justin Jefferson"
    assert rows[0].drafted_by == "Draft User"
    assert rows[0].amount == 25.0


# The drafter filter should compare stable user IDs rather than display names.
def test_build_draft_result_rows_filters_drafter() -> None:
    picks = [
        DraftPickModel(1, "player-1", "First Player", 25.0, "user-1"),
        DraftPickModel(2, "player-2", "Second Player", 10.0, "user-2"),
    ]

    rows = build_draft_result_rows(
        picks,
        {},
        {"user-1": "First User", "user-2": "Second User"},
        drafted_by_user_id="user-2",
    )

    assert len(rows) == 1
    assert rows[0].pick_number == 2
    assert rows[0].drafted_by == "Second User"
