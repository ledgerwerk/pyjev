"""Play Connect Four against Jev with exact bounded tactical proofs."""

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from pyjev import ChoiceResult, Jev

ROWS = 6
COLUMNS = 7
EMPTY = "."
HUMAN = "x"
JEV_PIECE = "o"
STRATEGIES = ("balanced", "aggressive", "defensive")

QUESTION = (
    "Choose the strongest Connect Four move from the supplied candidate columns. "
    "The game engine has already computed gravity, resulting boards, immediate wins, "
    "immediate opponent winning replies, and short exact forcing-line constraints. "
    "Treat those facts as authoritative. Choose only among the supplied candidate labels."
)

DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))


@dataclass(frozen=True, slots=True)
class Player:
    """A player/controller description used by human and Jev turns."""

    name: str
    piece: str
    controller: str = "jev"
    strategy: str = "balanced"


@dataclass(frozen=True, slots=True)
class StrategyProfile:
    """Prompt guidance applied only after exact tactical filtering."""

    name: str
    instruction: str


STRATEGY_PROFILES = {
    "balanced": StrategyProfile("balanced", "Prefer a sound move with flexible future options."),
    "aggressive": StrategyProfile("aggressive", "Among the supplied safe moves, prefer active counterplay."),
    "defensive": StrategyProfile("defensive", "Among the supplied safe moves, prefer reducing counterplay."),
}


@dataclass(slots=True)
class TacticalSelection:
    """The complete deterministic tactical preprocessing result for one turn."""

    legal_columns: list[int]
    candidates: list[int]
    reason: str
    constraints: list[str]
    rejected: dict[int, list[str]]
    analyses: dict[int, dict[str, object]]
    forcing_reply_proofs: dict[int, dict[int, dict[str, object]]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        """Return a one-based, JSON-safe compact selection summary."""
        return {
            "legal_columns": [column + 1 for column in self.legal_columns],
            "candidates": [column + 1 for column in self.candidates],
            "reason": self.reason,
            "constraints": list(self.constraints),
            "rejected": {str(column + 1): list(reasons) for column, reasons in sorted(self.rejected.items())},
        }


def new_board() -> list[list[str]]:
    """Return an empty six-row by seven-column board."""
    return [[EMPTY for _ in range(COLUMNS)] for _ in range(ROWS)]


def piece_owner(piece: str) -> str:
    """Return the human-readable owner of a board piece."""
    if piece == HUMAN:
        return "YOU"
    if piece == JEV_PIECE:
        return "JEV"
    raise ValueError(f"unknown piece: {piece!r}")


def render_board(
    board: list[list[str]],
    *,
    turn_piece: str | None = None,
    last_move: tuple[str, int] | None = None,
) -> str:
    """Render a board with identity, turn, and one-based column labels."""
    turn = "GAME OVER" if turn_piece is None else f"{piece_owner(turn_piece)} ({turn_piece})"
    lines = [
        f"YOU = {HUMAN}    JEV = {JEV_PIECE}    TURN = {turn}",
        "",
        "    " + " ".join(str(column) for column in range(1, COLUMNS + 1)),
        "  +" + "-" * (COLUMNS * 2 + 1) + "+",
    ]
    for row in board:
        lines.append("  | " + " ".join(row) + " |")
    lines.append("  +" + "-" * (COLUMNS * 2 + 1) + "+")
    if last_move is not None:
        piece, column = last_move
        lines.extend(["", f"last move: {piece_owner(piece)} ({piece}) -> column {column + 1}"])
    return "\n".join(lines)


def legal_columns(board: list[list[str]]) -> list[int]:
    """Return zero-based columns that still have room for a piece."""
    return [column for column in range(COLUMNS) if board[0][column] == EMPTY]


def landing_row(board: list[list[str]], column: int) -> int | None:
    """Return the zero-based row where a piece lands, or None if full."""
    for row in range(ROWS - 1, -1, -1):
        if board[row][column] == EMPTY:
            return row
    return None


def drop_piece(board: list[list[str]], column: int, piece: str) -> int:
    """Drop a piece into a column and return the row it occupies."""
    row = landing_row(board, column)
    if row is None:
        raise ValueError(f"column {column + 1} is full")
    board[row][column] = piece
    return row


def has_four(board: list[list[str]], piece: str) -> bool:
    """Return whether piece occupies four contiguous cells in any direction."""
    for row in range(ROWS):
        for column in range(COLUMNS):
            if board[row][column] != piece:
                continue
            for row_step, column_step in DIRECTIONS:
                if all(
                    0 <= row + step * row_step < ROWS
                    and 0 <= column + step * column_step < COLUMNS
                    and board[row + step * row_step][column + step * column_step] == piece
                    for step in range(1, 4)
                ):
                    return True
    return False


def board_state(board: list[list[str]]) -> list[str]:
    """Serialize the board from top row to bottom row."""
    return ["".join(row) for row in board]


def copy_board(board: list[list[str]]) -> list[list[str]]:
    """Return a shallow row-by-row copy suitable for move simulation."""
    return [row[:] for row in board]


def board_after_move(board: list[list[str]], column: int, piece: str) -> list[list[str]]:
    """Return the board after dropping a piece, leaving the original untouched."""
    after = copy_board(board)
    drop_piece(after, column, piece)
    return after


def winning_columns(board: list[list[str]], piece: str) -> list[int]:
    """Return zero-based legal columns that win immediately for piece."""
    wins: list[int] = []
    for column in legal_columns(board):
        after = board_after_move(board, column, piece)
        if has_four(after, piece):
            wins.append(column)
    return wins


def analyze_opponent_reply(
    board_after_candidate: list[list[str]],
    reply_column: int,
    *,
    piece: str,
    opponent: str,
) -> dict[str, object]:
    """Prove whether an opponent reply leaves an unavoidable immediate win."""
    after_reply = board_after_move(board_after_candidate, reply_column, opponent)
    opponent_wins_now = has_four(after_reply, opponent)
    if opponent_wins_now:
        return {
            "column": reply_column + 1,
            "board_after_reply": board_state(after_reply),
            "opponent_wins_now": True,
            "your_immediate_winning_responses": [],
            "opponent_winning_columns_next": [],
            "response_analysis": {},
            "escape_responses": [],
            "forces_loss_next_turn": True,
        }

    your_immediate_wins = winning_columns(after_reply, piece)
    response_analysis: dict[str, dict[str, object]] = {}
    escape_responses: list[int] = []
    for response in legal_columns(after_reply):
        after_response = board_after_move(after_reply, response, piece)
        wins_now = has_four(after_response, piece)
        opponent_wins_after_response = [] if wins_now else winning_columns(after_response, opponent)
        is_escape = wins_now or not opponent_wins_after_response
        if is_escape:
            escape_responses.append(response)
        response_analysis[str(response + 1)] = {
            "column": response + 1,
            "wins_now": wins_now,
            "opponent_winning_replies": [column + 1 for column in opponent_wins_after_response],
            "is_tactical_escape": is_escape,
        }

    return {
        "column": reply_column + 1,
        "board_after_reply": board_state(after_reply),
        "opponent_wins_now": False,
        "your_immediate_winning_responses": [column + 1 for column in your_immediate_wins],
        "opponent_winning_columns_next": [column + 1 for column in winning_columns(after_reply, opponent)],
        "response_analysis": response_analysis,
        "escape_responses": [column + 1 for column in escape_responses],
        "forces_loss_next_turn": not escape_responses,
    }


def opponent_forcing_replies(
    board: list[list[str]],
    candidate_column: int,
    *,
    piece: str,
    opponent: str,
) -> dict[int, dict[str, object]]:
    """Return exact opponent replies that prove a loss on the following turn."""
    after_candidate = board_after_move(board, candidate_column, piece)
    if has_four(after_candidate, piece):
        return {}
    forcing: dict[int, dict[str, object]] = {}
    for reply in legal_columns(after_candidate):
        proof = analyze_opponent_reply(
            after_candidate,
            reply,
            piece=piece,
            opponent=opponent,
        )
        if proof["forces_loss_next_turn"]:
            forcing[reply] = proof
    return forcing


def move_forces_win_next_turn(
    board: list[list[str]],
    candidate_column: int,
    *,
    piece: str,
    opponent: str,
) -> bool:
    """Return whether every non-winning opponent reply leaves an immediate win."""
    after_candidate = board_after_move(board, candidate_column, piece)
    if has_four(after_candidate, piece):
        return True
    replies = legal_columns(after_candidate)
    if not replies:
        return False
    for reply in replies:
        after_reply = board_after_move(after_candidate, reply, opponent)
        if has_four(after_reply, opponent):
            return False
        if not winning_columns(after_reply, piece):
            return False
    return True


def analyze_move(
    board: list[list[str]],
    column: int,
    piece: str,
    opponent: str,
) -> dict[str, object]:
    """Describe exact one-ply and bounded second-horizon consequences."""
    before_opponent_wins = winning_columns(board, opponent)
    row = landing_row(board, column)
    if row is None:
        raise ValueError(f"column {column + 1} is full")

    after = board_after_move(board, column, piece)
    wins_now = has_four(after, piece)
    opponent_winning_replies = winning_columns(after, opponent)
    your_winning_columns_next = winning_columns(after, piece)
    blocked = [threat for threat in before_opponent_wins if threat not in opponent_winning_replies]
    forcing = opponent_forcing_replies(board, column, piece=piece, opponent=opponent)
    compact_forcing = [
        {
            "column": reply + 1,
            "opponent_wins_now": proof["opponent_wins_now"],
            "opponent_winning_columns_next": proof["opponent_winning_columns_next"],
        }
        for reply, proof in sorted(forcing.items())
    ]
    return {
        "column": column + 1,
        "landing_cell": {"row": row + 1, "column": column + 1},
        "board_after": board_state(after),
        "wins_now": wins_now,
        "opponent_winning_replies": [reply + 1 for reply in opponent_winning_replies],
        "your_winning_columns_next": [reply + 1 for reply in your_winning_columns_next],
        "blocks_current_opponent_wins": [threat + 1 for threat in blocked],
        "allows_immediate_loss": not wins_now and bool(opponent_winning_replies),
        "opponent_forcing_replies": compact_forcing,
        "allows_forced_loss_next_turn": bool(forcing),
        "creates_forced_win_next_turn": move_forces_win_next_turn(
            board,
            column,
            piece=piece,
            opponent=opponent,
        ),
    }


def scan_tactics(board: list[list[str]], piece: str, opponent: str) -> TacticalSelection:
    """Compute one deterministic tactical selection for the current turn."""
    legal = legal_columns(board)
    if not legal:
        return TacticalSelection([], [], "no-legal-moves", [], {}, {})

    analyses = {column: analyze_move(board, column, piece, opponent) for column in legal}
    forcing_proofs = {
        column: opponent_forcing_replies(board, column, piece=piece, opponent=opponent) for column in legal
    }
    immediate_wins = winning_columns(board, piece)
    if immediate_wins:
        return TacticalSelection(legal, immediate_wins, "immediate-win", [], {}, analyses, forcing_proofs)

    safe = [column for column in legal if not analyses[column]["opponent_winning_replies"]]
    opponent_wins_now = winning_columns(board, opponent)
    if not safe:
        rejected = {column: ["immediate-opponent-win"] for column in legal}
        return TacticalSelection(
            legal,
            legal,
            "forced-loss-or-no-safe-one-ply-move",
            [],
            rejected,
            analyses,
            forcing_proofs,
        )

    constraints: list[str] = []
    if opponent_wins_now:
        constraints.append("forced-defense")
    elif len(safe) < len(legal):
        constraints.append("avoid-immediate-loss")

    forcing_wins = [
        column for column in safe if move_forces_win_next_turn(board, column, piece=piece, opponent=opponent)
    ]
    if forcing_wins:
        rejected = {column: ["not-a-proven-forcing-win"] for column in safe if column not in forcing_wins}
        return TacticalSelection(
            legal,
            forcing_wins,
            "forced-win-next-turn",
            constraints + ["forced-win-next-turn"],
            rejected,
            analyses,
            forcing_proofs,
        )

    deep_safe = [column for column in safe if not forcing_proofs[column]]
    rejected: dict[int, list[str]] = {}
    for column in legal:
        if column not in safe:
            rejected[column] = ["immediate-opponent-win"]
        elif column not in deep_safe:
            rejected[column] = ["opponent-forcing-reply"]

    if deep_safe and len(deep_safe) < len(safe):
        return TacticalSelection(
            legal,
            deep_safe,
            "avoid-forced-loss-next-turn",
            constraints + ["avoid-forced-loss-next-turn"],
            rejected,
            analyses,
            forcing_proofs,
        )
    if not deep_safe:
        return TacticalSelection(
            legal,
            safe,
            "forced-loss-next-turn-or-no-deep-safe-move",
            constraints,
            {column: reasons for column, reasons in rejected.items() if column not in safe},
            analyses,
            forcing_proofs,
        )
    if len(safe) < len(legal):
        reason = "forced-defense" if opponent_wins_now else "avoid-immediate-loss"
    else:
        reason = "strategic-choice"
    return TacticalSelection(legal, deep_safe, reason, constraints, rejected, analyses, forcing_proofs)


def tactical_candidates(
    board: list[list[str]],
    piece: str,
    opponent: str,
) -> tuple[list[int], str]:
    """Compatibility wrapper returning the tactical selection tuple."""
    selection = scan_tactics(board, piece, opponent)
    return selection.candidates, selection.reason


def board_ascii(board: list[list[str]]) -> str:
    """Render rows with explicit top/bottom and left-to-right orientation."""
    lines = ["columns  1 2 3 4 5 6 7"]
    for row_number, row in enumerate(board, start=1):
        suffix = "  <- top" if row_number == 1 else ""
        if row_number == ROWS:
            suffix = "  <- bottom"
        lines.append(f"row {row_number}:  {' '.join(row)}{suffix}")
    return "\n".join(lines)


def build_jev_state(
    board: list[list[str]],
    candidate_columns: list[int],
    candidate_reason: str,
    *,
    piece: str = JEV_PIECE,
    opponent: str = HUMAN,
    selection: TacticalSelection | None = None,
    player: Player | None = None,
    opponent_player: Player | None = None,
) -> dict[str, object]:
    """Build exact tactical state supplied to Jev."""
    selection = selection or scan_tactics(board, piece, opponent)
    legal = selection.legal_columns
    analyses = {str(column + 1): selection.analyses[column] for column in legal}
    active_name = player.name if player else ("Jev" if piece == JEV_PIECE else "Jev-X")
    other_name = opponent_player.name if opponent_player else ("human" if opponent == HUMAN else "Jev-O")
    strategy = player.strategy if player else "balanced"
    return {
        "game": "Connect Four",
        "perspective": {
            "you": {"name": active_name, "piece": piece},
            "opponent": {"name": other_name, "piece": opponent},
            "turn": {"name": active_name, "piece": piece},
            "strategy": strategy,
        },
        "coordinates": {
            "columns": "1 through 7 from left to right",
            "rows": "1 through 6 from top to bottom",
            "gravity": "a piece lands in the lowest empty cell of its column",
        },
        "board_rows": board_state(board),
        "board_ascii": board_ascii(board),
        "legal_columns": [column + 1 for column in legal],
        "move_number": 1 + sum(cell != EMPTY for row in board for cell in row),
        "tactical_facts": {
            "your_winning_columns_now": [column + 1 for column in winning_columns(board, piece)],
            "opponent_winning_columns_now": [column + 1 for column in winning_columns(board, opponent)],
            "constraints_applied": list(selection.constraints),
            "candidate_reason": candidate_reason,
            "candidate_columns": [column + 1 for column in candidate_columns],
            "rejected_columns": {str(column + 1): reasons for column, reasons in sorted(selection.rejected.items())},
        },
        "move_analysis": analyses,
        "rules": [
            "Four equal pieces horizontally, vertically, or diagonally wins immediately.",
            "Only listed legal columns may be played.",
            "The supplied tactical facts were computed exactly by the game engine.",
            "Short forcing proofs are bounded tactical facts, not strategic evaluation.",
        ],
    }


def jev_choices(
    board: list[list[str]],
    candidates: list[int],
    *,
    piece: str = JEV_PIECE,
    opponent: str = HUMAN,
    selection: TacticalSelection | None = None,
) -> dict[str, dict[str, object]]:
    """Build structured Choice criteria for final candidate columns only."""
    selection = selection or scan_tactics(board, piece, opponent)
    return {str(column + 1): selection.analyses[column] for column in candidates}


def question_for_strategy(strategy: str) -> str:
    """Return the base question plus post-filter strategy guidance."""
    if strategy not in STRATEGY_PROFILES:
        raise ValueError(f"unknown strategy: {strategy!r}")
    return QUESTION + " " + STRATEGY_PROFILES[strategy].instruction


def choose_jev_column(
    jev: Jev,
    board: list[list[str]],
    *,
    player: Player | None = None,
    opponent: Player | None = None,
    selection: TacticalSelection | None = None,
    candidates: list[int] | None = None,
    reason: str | None = None,
    debug: bool = False,
) -> tuple[int, ChoiceResult | None, str]:
    """Choose a move, bypassing Jev when Python proves only one candidate."""
    active_piece = player.piece if player else JEV_PIECE
    opponent_piece = opponent.piece if opponent else HUMAN
    strategy = player.strategy if player else "balanced"
    if selection is None:
        if candidates is not None or reason is not None:
            selection = scan_tactics(board, active_piece, opponent_piece)
            if candidates is not None:
                selection.candidates = list(candidates)
            if reason is not None:
                selection.reason = reason
        else:
            selection = scan_tactics(board, active_piece, opponent_piece)
    candidates = selection.candidates
    reason = selection.reason
    if not candidates:
        raise RuntimeError("no Jev move available")
    if len(candidates) == 1:
        return candidates[0], None, reason

    state = build_jev_state(
        board,
        candidates,
        reason,
        piece=active_piece,
        opponent=opponent_piece,
        selection=selection,
        player=player,
        opponent_player=opponent,
    )
    choices = jev_choices(
        board,
        candidates,
        piece=active_piece,
        opponent=opponent_piece,
        selection=selection,
    )
    question = question_for_strategy(strategy)
    if debug:
        print("\nquestion sent to Jev:")
        print(question)
        print("\nstate sent to Jev:")
        print(json.dumps(state, indent=2, sort_keys=True))
        print("\nchoices sent to Jev:")
        print(json.dumps(choices, indent=2, sort_keys=True))
    result = jev.choice(question, state=state, choices=choices)
    if debug:
        print_jev_response(result)
    try:
        column = int(result.value) - 1
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Jev returned a non-numeric column: {result.value!r}") from exc
    if column not in candidates:
        raise RuntimeError(f"Jev returned a non-candidate column: {result.value!r}")
    return column, result, reason


def print_tactical_scan(
    selection_or_board: TacticalSelection | list[list[str]],
    candidates: list[int] | None = None,
    reason: str | None = None,
    *,
    piece: str = JEV_PIECE,
    opponent: str = HUMAN,
    strategy: str | None = None,
) -> None:
    """Print compact deterministic tactical conclusions."""
    if isinstance(selection_or_board, TacticalSelection):
        selection = selection_or_board
    else:
        selection = scan_tactics(selection_or_board, piece, opponent)
        if candidates is not None:
            selection.candidates = candidates
        if reason is not None:
            selection.reason = reason
    actor = "JEV" if piece == JEV_PIECE else f"JEV-{piece.upper()}"
    suffix = f" [{strategy}]" if strategy else ""
    immediate_own = winning_columns_from_selection(selection, "own")
    immediate_opponent = winning_columns_from_selection(selection, "opponent")
    print(f"\nTactical scan for {actor}{suffix}:")
    print("  immediate own wins: " + (" ".join(map(str, immediate_own)) or "none"))
    print("  immediate opponent wins: " + (" ".join(map(str, immediate_opponent)) or "none"))
    rejected = sorted(column + 1 for column in selection.rejected)
    if rejected:
        print("  rejected by short forcing proof: " + " ".join(map(str, rejected)))
    print("  candidate columns: " + (" ".join(str(column + 1) for column in selection.candidates) or "none"))


def winning_columns_from_selection(selection: TacticalSelection, side: str) -> list[int]:
    """Read immediate facts from the selection without recomputing proof trees."""
    if side == "own":
        return _analysis_winning_columns(selection, "wins_now")
    return _analysis_winning_columns(selection, "allows_immediate_loss")


def _analysis_winning_columns(selection: TacticalSelection, key: str) -> list[int]:
    """Internal compatibility helper for compact terminal output."""
    if key == "wins_now":
        return [column + 1 for column, analysis in selection.analyses.items() if analysis["wins_now"]]
    return sorted({reply for analysis in selection.analyses.values() for reply in analysis["opponent_winning_replies"]})


def print_tactical_debug(
    board: list[list[str]],
    selection: TacticalSelection,
    *,
    piece: str,
    opponent: str,
    strategy: str | None = None,
) -> None:
    """Print candidate matrices and full forcing proof branches."""
    actor = "JEV" if piece == JEV_PIECE else f"JEV-{piece.upper()}"
    print("\n=== tactical debug ===")
    print(f"actor: {actor} ({piece})")
    print(f"move number: {1 + sum(cell != EMPTY for row in board for cell in row)}")
    print("legal columns: " + " ".join(str(column + 1) for column in selection.legal_columns))
    print("immediate own wins: " + (" ".join(map(str, winning_columns_from_selection(selection, "own"))) or "none"))
    print(
        "immediate opponent wins: "
        + (" ".join(map(str, winning_columns_from_selection(selection, "opponent"))) or "none")
    )
    if strategy:
        print(f"strategy: {strategy}")
    for column in selection.legal_columns:
        analysis = selection.analyses[column]
        print(f"\ncandidate {column + 1}:")
        print(f"  wins now: {'yes' if analysis['wins_now'] else 'no'}")
        immediate = analysis["opponent_winning_replies"]
        print("  opponent immediate wins after move: " + (" ".join(map(str, immediate)) or "none"))
        forcing = selection.forcing_reply_proofs.get(column, {})
        if forcing:
            formatted = " ".join(
                f"{reply + 1}->[{', '.join(map(str, proof['opponent_winning_columns_next']))}]"
                for reply, proof in sorted(forcing.items())
            )
            print(f"  forcing opponent replies (opponent forcing replies): {formatted}")
        else:
            print("  opponent forcing replies: none")
        if column in selection.rejected:
            print("  result: rejected (" + ", ".join(selection.rejected[column]) + ")")
        else:
            print("  result: kept")
    for column, proofs in sorted(selection.forcing_reply_proofs.items()):
        for reply, proof in sorted(proofs.items()):
            print_forcing_proof(column, reply, proof)
    print("\ntactical constraints applied:")
    for constraint in selection.constraints:
        print(f"  - {constraint}")
    print("legal columns:      " + " ".join(str(column + 1) for column in selection.legal_columns))
    print("rejected columns:   " + (" ".join(str(column + 1) for column in sorted(selection.rejected)) or "none"))
    print("final candidates:   " + (" ".join(str(column + 1) for column in selection.candidates) or "none"))


def print_forcing_proof(candidate: int, reply: int, proof: dict[str, object]) -> None:
    """Print one exact candidate -> reply -> response proof."""
    print(f"\nproof: candidate {candidate + 1} -> opponent reply {reply + 1}")
    print("board after opponent reply:")
    for row in proof["board_after_reply"]:
        print("  " + " ".join(row))
    print(
        "opponent immediate winning columns next: "
        + (" ".join(map(str, proof["opponent_winning_columns_next"])) or "none")
    )
    print("our legal responses:")
    response_analysis = proof["response_analysis"]
    for response, details in response_analysis.items():
        if details["wins_now"]:
            print(f"  {response} -> own immediate win (escape)")
        else:
            wins = details["opponent_winning_replies"]
            print(f"  {response} -> opponent still wins: " + (" ".join(map(str, wins)) or "none"))
    print("escape responses: " + (" ".join(map(str, proof["escape_responses"])) or "none"))
    print(
        "proof result: opponent reply "
        + str(reply + 1)
        + (" forces loss next turn" if proof["forces_loss_next_turn"] else " is not forcing")
    )


def print_forced_jev_move(column: int, reason: str) -> None:
    """Explain a deterministic move that did not require a Jev call."""
    label = "winning move" if reason == "immediate-win" else "move"
    print(f"\nJev forced {label}: column {column + 1}")
    print("(no model call: only one tactically valid move)")


def print_jev_response(result: ChoiceResult) -> None:
    """Print safe ChoiceResult metadata without credentials."""
    print("\nJev response:")
    print(f"  selected: {result.value}")
    print(f"  confidence: {result.confidence:.2f}")
    print(f"  model: {result.model}")
    print(f"  request_id: {result.request_id}")
    print("  probabilities:")
    for label, probability in sorted(result.probabilities.items()):
        print(f"    {label}: {probability:.3f}")
    print("  raw:")
    print(json.dumps(result.raw, indent=2, sort_keys=True))
    print("  usage:")
    print(json.dumps(result.usage, indent=2, sort_keys=True))


def print_jev_result(
    result: ChoiceResult,
    reason: str,
    legal: list[int],
    candidates: list[int],
) -> None:
    """Print a real Jev decision and its complete candidate distribution."""
    print(f"\nJev decision: column {result.value}")
    print(f"candidate reason: {reason}")
    print(f"confidence: {result.confidence:.2f}")
    if legal != candidates:
        print("legal columns:     " + " ".join(str(column + 1) for column in legal))
        print("Jev candidates:    " + " ".join(str(column + 1) for column in candidates))
    print("candidate probabilities:")
    for label, probability in sorted(result.probabilities.items(), key=lambda item: item[1], reverse=True):
        selected = "  <-- selected" if label == result.value else ""
        print(f"  {label}  {probability:6.1%}{selected}")


def append_trace(path: Path, record: dict[str, object]) -> None:
    """Append one safe JSONL turn record."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def trace_model_result(result: ChoiceResult | None) -> dict[str, object]:
    """Serialize only non-secret ChoiceResult metadata."""
    if result is None:
        return {"performed": False, "reason": "single-tactical-candidate"}
    return {
        "performed": True,
        "selected": result.value,
        "confidence": result.confidence,
        "probabilities": result.probabilities,
        "model": result.model,
        "request_id": result.request_id,
        "usage": result.usage,
        "raw": result.raw,
    }


def trace_record(
    *,
    turn: int,
    player: Player,
    board_before: list[list[str]],
    selection: TacticalSelection,
    result: ChoiceResult | None,
    selected_column: int,
    board_after: list[list[str]],
) -> dict[str, object]:
    """Build a credential-free completed-turn trace record."""
    return {
        "turn": turn,
        "actor": {
            "name": player.name,
            "piece": player.piece,
            "controller": player.controller,
            "strategy": player.strategy,
        },
        "board_before": board_state(board_before),
        "tactical": selection.as_dict(),
        "model_call": trace_model_result(result),
        "selected_column": selected_column + 1,
        "board_after": board_state(board_after),
    }


def prompt_human_column(board: list[list[str]]) -> int | None:
    """Prompt until the human enters a legal zero-based column or quits."""
    while True:
        try:
            raw = input("\nYour move [1-7, q]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw in {"q", "quit"}:
            return None
        try:
            number = int(raw)
        except ValueError:
            print("Please enter a column from 1 to 7, or q to quit.")
            continue
        if not 1 <= number <= COLUMNS:
            print("Column must be between 1 and 7.")
            continue
        column = number - 1
        if column not in legal_columns(board):
            print(f"Column {number} is full. Choose another column.")
            continue
        return column


def other_piece(piece: str) -> str:
    """Return the other Connect Four piece."""
    if piece == HUMAN:
        return JEV_PIECE
    if piece == JEV_PIECE:
        return HUMAN
    raise ValueError(f"unknown piece: {piece!r}")


def build_players(strategy: str = "balanced", *, self_play: bool = False) -> tuple[Player, Player]:
    """Build the player-relative pair used by the demo."""
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy!r}")
    if self_play:
        return (
            Player("Jev-X", "x", "jev", strategy),
            Player("Jev-O", "o", "jev", strategy),
        )
    return Player("human", HUMAN, "human"), Player("Jev", JEV_PIECE, "jev", strategy)


def _record_human_turn(
    trace: Path | None,
    turn: int,
    player: Player,
    board_before: list[list[str]],
    column: int,
    board_after: list[list[str]],
) -> None:
    if trace is None:
        return
    selection = TacticalSelection(legal_columns(board_before), [column], "human-input", [], {}, {})
    append_trace(
        trace,
        trace_record(
            turn=turn,
            player=player,
            board_before=board_before,
            selection=selection,
            result=None,
            selected_column=column,
            board_after=board_after,
        ),
    )


def play_self_game(jev: Jev, *, strategy: str, debug: bool, trace: Path | None) -> None:
    """Run a player-relative Jev-vs-Jev game using the same tactical filter."""
    players = build_players(strategy, self_play=True)
    board = new_board()
    active_index = 0
    turn = 1
    while True:
        player = players[active_index]
        opponent = players[1 - active_index]
        selection = scan_tactics(board, player.piece, opponent.piece)
        print(render_board(board, turn_piece=player.piece))
        print_tactical_scan(selection, piece=player.piece, opponent=opponent.piece, strategy=player.strategy)
        if debug:
            print_tactical_debug(
                board,
                selection,
                piece=player.piece,
                opponent=opponent.piece,
                strategy=player.strategy,
            )
        if not selection.candidates:
            print("\nDraw: the board is full.")
            return
        board_before = copy_board(board)
        column, result, reason = choose_jev_column(
            jev,
            board,
            player=player,
            opponent=opponent,
            selection=selection,
            debug=debug,
        )
        if result is None:
            print_forced_jev_move(column, reason)
        else:
            print_jev_result(result, reason, selection.legal_columns, selection.candidates)
        drop_piece(board, column, player.piece)
        if trace is not None:
            append_trace(
                trace,
                trace_record(
                    turn=turn,
                    player=player,
                    board_before=board_before,
                    selection=selection,
                    result=result,
                    selected_column=column,
                    board_after=board,
                ),
            )
        if has_four(board, player.piece):
            print(render_board(board, turn_piece=None, last_move=(player.piece, column)))
            print(f"\n{player.name} wins!")
            return
        if not legal_columns(board):
            print(render_board(board, turn_piece=None, last_move=(player.piece, column)))
            print("\nDraw: the board is full.")
            return
        active_index = 1 - active_index
        turn += 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse demo-only controls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--debug", action="store_true", help="print full tactical and Jev request diagnostics")
    parser.add_argument("--trace", type=Path, help="append credential-free JSONL turn records to PATH")
    parser.add_argument("--strategy", choices=STRATEGIES, default="balanced")
    parser.add_argument("--self-play", action="store_true", help="run Jev-X versus Jev-O instead of human play")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run an interactive human-versus-Jev or Jev-vs-Jev game."""
    args = parse_args(argv)
    if args.trace is not None:
        args.trace.parent.mkdir(parents=True, exist_ok=True)
    print("=== Connect Four ===")
    print("Get four in a row horizontally, vertically, or diagonally.")
    if args.self_play:
        print(f"Jev-vs-Jev ({args.strategy} strategy)")
        try:
            with Jev() as jev:
                play_self_game(jev, strategy=args.strategy, debug=args.debug, trace=args.trace)
        except KeyboardInterrupt:
            print("\nGame ended.")
        return

    board = new_board()
    last_move: tuple[str, int] | None = None
    human = Player("human", HUMAN, "human")
    jev_player = Player("Jev", JEV_PIECE, "jev", args.strategy)
    try:
        with Jev() as jev:
            while True:
                print(render_board(board, turn_piece=HUMAN, last_move=last_move))
                human_before = copy_board(board)
                human_column = prompt_human_column(board)
                if human_column is None:
                    print("Game ended.")
                    return
                drop_piece(board, human_column, HUMAN)
                last_move = (HUMAN, human_column)
                _record_human_turn(
                    args.trace,
                    1 + sum(cell != EMPTY for row in human_before for cell in row),
                    human,
                    human_before,
                    human_column,
                    board,
                )
                if has_four(board, HUMAN):
                    print(render_board(board, turn_piece=None, last_move=last_move))
                    print("\nYou win!")
                    return
                if not legal_columns(board):
                    print(render_board(board, turn_piece=None, last_move=last_move))
                    print("\nDraw: the board is full.")
                    return

                print(render_board(board, turn_piece=JEV_PIECE, last_move=last_move))
                selection = scan_tactics(board, jev_player.piece, human.piece)
                print_tactical_scan(
                    selection,
                    piece=jev_player.piece,
                    opponent=human.piece,
                    strategy=jev_player.strategy,
                )
                if args.debug:
                    print_tactical_debug(
                        board,
                        selection,
                        piece=jev_player.piece,
                        opponent=human.piece,
                        strategy=jev_player.strategy,
                    )
                before_jev = copy_board(board)
                jev_column, result, reason = choose_jev_column(
                    jev,
                    board,
                    player=jev_player,
                    opponent=human,
                    selection=selection,
                    debug=args.debug,
                )
                if result is None:
                    print_forced_jev_move(jev_column, reason)
                else:
                    print_jev_result(result, reason, selection.legal_columns, selection.candidates)
                drop_piece(board, jev_column, JEV_PIECE)
                if args.trace is not None:
                    append_trace(
                        args.trace,
                        trace_record(
                            turn=1 + sum(cell != EMPTY for row in before_jev for cell in row),
                            player=jev_player,
                            board_before=before_jev,
                            selection=selection,
                            result=result,
                            selected_column=jev_column,
                            board_after=board,
                        ),
                    )
                last_move = (JEV_PIECE, jev_column)
                if has_four(board, JEV_PIECE):
                    print(render_board(board, turn_piece=None, last_move=last_move))
                    print("\nJev wins!")
                    return
                if not legal_columns(board):
                    print(render_board(board, turn_piece=None, last_move=last_move))
                    print("\nDraw: the board is full.")
                    return
    except KeyboardInterrupt:
        print("\nGame ended.")


if __name__ == "__main__":
    main()
