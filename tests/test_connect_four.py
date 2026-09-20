from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest


@pytest.fixture(scope="module")
def connect_four() -> ModuleType:
    path = Path(__file__).parents[1] / "examples" / "connect_four.py"
    spec = importlib.util.spec_from_file_location("connect_four_example", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def regression_board() -> list[list[str]]:
    return [
        list("......."),
        list("......."),
        list("......."),
        list("...o.x."),
        list("...oxo."),
        list("..xxxo."),
    ]


def test_render_board_keeps_identity_and_orientation_visible(connect_four: ModuleType) -> None:
    rendered = connect_four.render_board(
        connect_four.new_board(),
        turn_piece=connect_four.JEV_PIECE,
        last_move=(connect_four.HUMAN, 2),
    )

    assert "YOU = x    JEV = o    TURN = JEV (o)" in rendered
    assert "last move: YOU (x) -> column 3" in rendered
    assert "1 2 3 4 5 6 7" in rendered

    ascii_board = connect_four.board_ascii(connect_four.new_board())
    assert ascii_board.startswith("columns  1 2 3 4 5 6 7")
    assert "row 1:" in ascii_board and "<- top" in ascii_board
    assert "row 6:" in ascii_board and "<- bottom" in ascii_board


def test_regression_position_forces_column_two_defense(connect_four: ModuleType) -> None:
    board = regression_board()

    assert [column + 1 for column in connect_four.winning_columns(board, connect_four.HUMAN)] == [2]
    candidates, reason = connect_four.tactical_candidates(
        board,
        connect_four.JEV_PIECE,
        connect_four.HUMAN,
    )

    assert reason == "forced-defense"
    assert [column + 1 for column in candidates] == [2]
    assert board == regression_board()


def test_analyze_move_contains_exact_candidate_facts(connect_four: ModuleType) -> None:
    analysis = connect_four.analyze_move(regression_board(), 1, connect_four.JEV_PIECE, connect_four.HUMAN)

    assert analysis["landing_cell"] == {"row": 6, "column": 2}
    assert analysis["board_after"][-1] == ".oxxxo."
    assert analysis["wins_now"] is False
    assert analysis["opponent_winning_replies"] == []
    assert analysis["blocks_current_opponent_wins"] == [2]
    assert analysis["allows_immediate_loss"] is False


def test_jev_immediate_win_takes_priority(connect_four: ModuleType) -> None:
    board = [
        list("......."),
        list("......."),
        list("......."),
        list("......."),
        list("......."),
        list("..ooo.."),
    ]

    candidates, reason = connect_four.tactical_candidates(board, connect_four.JEV_PIECE, connect_four.HUMAN)

    assert reason == "immediate-win"
    assert candidates == connect_four.winning_columns(board, connect_four.JEV_PIECE)


def test_avoid_immediate_loss_removes_giving_move(connect_four: ModuleType) -> None:
    board = [
        list("x......"),
        list("o......"),
        list("o......"),
        list("x..o..."),
        list("ox.xx.."),
        list("xx.oo.."),
    ]

    candidates, reason = connect_four.tactical_candidates(board, connect_four.JEV_PIECE, connect_four.HUMAN)

    assert reason == "forced-win-next-turn"
    assert [column + 1 for column in candidates] == [6]
    assert 2 not in candidates


def test_forced_loss_keeps_all_legal_moves(connect_four: ModuleType) -> None:
    board = [
        list("......."),
        list("......."),
        list("......."),
        list("xx....."),
        list("xx....."),
        list("xx....."),
    ]

    candidates, reason = connect_four.tactical_candidates(board, connect_four.JEV_PIECE, connect_four.HUMAN)

    assert reason == "forced-loss-or-no-safe-one-ply-move"
    assert candidates == connect_four.legal_columns(board)


def test_one_candidate_never_calls_jev(connect_four: ModuleType) -> None:
    board = [
        list("xoxoxo."),
        list("oxoxox."),
        list("xoxoxo."),
        list("oxoxox."),
        list("xoxoxo."),
        list("oxoxox."),
    ]
    jev = Mock()

    column, result, reason = connect_four.choose_jev_column(jev, board)

    assert column == 6
    assert result is None
    assert reason == "immediate-win"
    jev.choice.assert_not_called()


def test_structured_state_and_choices_include_all_tactical_data(connect_four: ModuleType) -> None:
    board = regression_board()
    state = connect_four.build_jev_state(board, [1], "forced-defense")
    choices = connect_four.jev_choices(board, [1])

    assert state["board_rows"] == [".......", ".......", ".......", "...o.x.", "...oxo.", "..xxxo."]
    assert "<- top" in state["board_ascii"]
    assert state["coordinates"]["gravity"]
    assert set(state["move_analysis"]) == {"1", "2", "3", "4", "5", "6", "7"}
    assert choices["2"]["opponent_winning_replies"] == []
    assert isinstance(choices["2"]["board_after"], list)


def test_invalid_jev_label_is_an_explicit_error(connect_four: ModuleType) -> None:
    board = connect_four.new_board()
    jev = Mock()
    jev.choice.return_value.value = "7"

    with pytest.raises(RuntimeError, match="non-candidate"):
        connect_four.choose_jev_column(jev, board, candidates=[0, 1], reason="strategic-choice")


def v3_board() -> list[list[str]]:
    return [
        list("......."),
        list("......."),
        list("......."),
        list("......."),
        list("...o..."),
        list("...xx.."),
    ]


def test_v3_candidate_four_has_both_forcing_replies(connect_four: ModuleType) -> None:
    forcing = connect_four.opponent_forcing_replies(
        v3_board(),
        3,
        piece=connect_four.JEV_PIECE,
        opponent=connect_four.HUMAN,
    )

    assert [column + 1 for column in forcing] == [3, 6]
    assert forcing[2]["opponent_winning_columns_next"] == [2, 6]
    assert forcing[5]["opponent_winning_columns_next"] == [3, 7]


def test_v3_scan_filters_observed_fork_before_jev(connect_four: ModuleType) -> None:
    selection = connect_four.scan_tactics(v3_board(), connect_four.JEV_PIECE, connect_four.HUMAN)

    assert selection.reason == "avoid-forced-loss-next-turn"
    assert [column + 1 for column in selection.candidates] == [3, 6]
    assert 3 in selection.rejected
    assert selection.rejected[3] == ["opponent-forcing-reply"]
    assert selection.forcing_reply_proofs[2] == {}
    assert selection.forcing_reply_proofs[5] == {}


def test_v3_immediate_win_is_an_escape(connect_four: ModuleType) -> None:
    board_after_candidate = [
        list("......."),
        list("......."),
        list("......."),
        list("......."),
        list("......."),
        list("ooo...x"),
    ]
    proof = connect_four.analyze_opponent_reply(
        board_after_candidate,
        6,
        piece=connect_four.JEV_PIECE,
        opponent=connect_four.HUMAN,
    )

    assert proof["your_immediate_winning_responses"] == [4]
    assert 4 in proof["escape_responses"]
    assert proof["forces_loss_next_turn"] is False


def test_v3_forced_win_next_turn_is_preferred(connect_four: ModuleType) -> None:
    board = [
        list("x......"),
        list("o......"),
        list("o......"),
        list("x..o..."),
        list("ox.xx.."),
        list("xx.oo.."),
    ]
    selection = connect_four.scan_tactics(board, connect_four.JEV_PIECE, connect_four.HUMAN)

    assert selection.reason == "forced-win-next-turn"
    assert [column + 1 for column in selection.candidates] == [6]


def test_v3_player_relative_filter_is_symmetric(connect_four: ModuleType) -> None:
    board = v3_board()
    swapped = [[{"x": "o", "o": "x"}.get(cell, cell) for cell in row] for row in board]
    original = connect_four.scan_tactics(board, "o", "x")
    mirrored = connect_four.scan_tactics(swapped, "x", "o")

    assert original.candidates == mirrored.candidates == [2, 5]
    assert original.reason == mirrored.reason == "avoid-forced-loss-next-turn"


def test_v3_strategy_does_not_change_tactical_selection(connect_four: ModuleType) -> None:
    board = v3_board()
    selections = [connect_four.scan_tactics(board, "o", "x") for _ in connect_four.STRATEGIES]

    assert [selection.as_dict() for selection in selections] == [selections[0].as_dict()] * 3
    assert connect_four.question_for_strategy("aggressive") != connect_four.question_for_strategy("defensive")


def test_v3_jev_choices_contain_only_final_candidates(connect_four: ModuleType) -> None:
    board = v3_board()
    selection = connect_four.scan_tactics(board, "o", "x")
    jev = Mock()
    jev.choice.return_value.value = "3"

    column, result, reason = connect_four.choose_jev_column(
        jev,
        board,
        selection=selection,
        debug=False,
    )

    assert (column, reason) == (2, "avoid-forced-loss-next-turn")
    assert result is jev.choice.return_value
    choices = jev.choice.call_args.kwargs["choices"]
    assert set(choices) == {"3", "6"}


def test_v3_debug_includes_proof_and_final_candidates(
    connect_four: ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    selection = connect_four.scan_tactics(v3_board(), "o", "x")
    connect_four.print_tactical_debug(v3_board(), selection, piece="o", opponent="x")
    output = capsys.readouterr().out

    assert "candidate 4" in output
    assert "forcing opponent replies" in output
    assert "2" in output and "6" in output
    assert "rejected" in output
    assert "final candidates:   3 6" in output


def test_v3_trace_is_jsonl_and_has_no_credentials(connect_four: ModuleType, tmp_path: Path) -> None:
    selection = connect_four.scan_tactics(v3_board(), "o", "x")
    player = connect_four.Player("Jev", "o", "jev", "balanced")
    path = tmp_path / "connect-four.jsonl"
    record = connect_four.trace_record(
        turn=4,
        player=player,
        board_before=v3_board(),
        selection=selection,
        result=None,
        selected_column=2,
        board_after=connect_four.board_after_move(v3_board(), 2, "o"),
    )
    connect_four.append_trace(path, record)

    loaded = json.loads(path.read_text())
    assert loaded["tactical"]["candidates"] == [3, 6]
    assert loaded["model_call"]["performed"] is False
    assert "api_key" not in json.dumps(loaded).lower()


def test_v3_single_deep_candidate_skips_jev(connect_four: ModuleType) -> None:
    board = [
        list("x......"),
        list("o......"),
        list("o......"),
        list("x..o..."),
        list("ox.xx.."),
        list("xx.oo.."),
    ]
    jev = Mock()
    column, result, reason = connect_four.choose_jev_column(jev, board)

    assert column == 5
    assert result is None
    assert reason == "forced-win-next-turn"
    jev.choice.assert_not_called()



def test_mechanics_cover_gravity_full_columns_and_win_directions(connect_four: ModuleType) -> None:
    board = connect_four.new_board()
    assert connect_four.drop_piece(board, 0, connect_four.HUMAN) == 5
    assert connect_four.drop_piece(board, 0, connect_four.JEV_PIECE) == 4

    for _ in range(4):
        connect_four.drop_piece(board, 1, connect_four.HUMAN)
    assert connect_four.has_four(board, connect_four.HUMAN)
    with pytest.raises(ValueError, match="full"):
        for _ in range(3):
            connect_four.drop_piece(board, 1, connect_four.JEV_PIECE)

    horizontal = [list("xxxx...")] + [list(".......") for _ in range(5)]
    vertical = [list("x......") for _ in range(4)] + [list(".......") for _ in range(2)]
    diagonal = [
        list("...x..."),
        list("..x...."),
        list(".x....."),
        list("x......"),
        list("......."),
        list("......."),
    ]
    other_diagonal = [
        list("x......"),
        list(".x....."),
        list("..x...."),
        list("...x..."),
        list("......."),
        list("......."),
    ]
    assert connect_four.has_four(horizontal, "x")
    assert connect_four.has_four(vertical, "x")
    assert connect_four.has_four(diagonal, "x")
    assert connect_four.has_four(other_diagonal, "x")


def test_full_board_without_winner_is_a_draw_state(connect_four: ModuleType) -> None:
    board = [
        list("xoxxoxx"),
        list("ooxoxoo"),
        list("oxoxoox"),
        list("oxooxxx"),
        list("xoxxxoo"),
        list("xoooxxo"),
    ]

    assert connect_four.legal_columns(board) == []
    assert not connect_four.has_four(board, connect_four.HUMAN)
    assert not connect_four.has_four(board, connect_four.JEV_PIECE)


@pytest.mark.parametrize("input_value", ["quit", EOFError, KeyboardInterrupt])
def test_prompt_handles_quit_eof_and_ctrl_c(
    connect_four: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    input_value: str | type[BaseException],
) -> None:
    if isinstance(input_value, str):
        monkeypatch.setattr("builtins.input", lambda _: input_value)
    else:

        def interrupted(_: str) -> str:
            raise input_value

        monkeypatch.setattr("builtins.input", interrupted)

    assert connect_four.prompt_human_column(connect_four.new_board()) is None
