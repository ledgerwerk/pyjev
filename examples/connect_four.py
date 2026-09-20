"""Play Connect Four against Jev in the terminal."""

from __future__ import annotations

from pyjev import ChoiceResult, Jev

ROWS = 6
COLUMNS = 7
EMPTY = "."
HUMAN = "x"
JEV_PIECE = "o"

QUESTION = (
    "Choose the strongest Connect Four move for Jev from the supplied candidate columns. "
    "The game engine has already computed gravity, resulting boards, immediate wins, "
    "immediate opponent winning replies, and forced tactical constraints. Treat those "
    "facts as authoritative. Prefer moves that create strong future winning chances and "
    "reduce the opponent's threats. Return only one of the supplied Choice labels."
)

DIRECTIONS = (
    (0, 1),
    (1, 0),
    (1, 1),
    (1, -1),
)


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
        lines.extend(
            [
                "",
                f"last move: {piece_owner(piece)} ({piece}) -> column {column + 1}",
            ]
        )
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


def analyze_move(
    board: list[list[str]],
    column: int,
    piece: str,
    opponent: str,
) -> dict[str, object]:
    """Describe the exact one-ply consequences of a candidate move."""
    before_opponent_wins = winning_columns(board, opponent)
    row = landing_row(board, column)
    if row is None:
        raise ValueError(f"column {column + 1} is full")

    after = board_after_move(board, column, piece)
    wins_now = has_four(after, piece)
    opponent_winning_replies = winning_columns(after, opponent)
    your_winning_columns_next = winning_columns(after, piece)
    blocked = [threat for threat in before_opponent_wins if threat not in opponent_winning_replies]

    return {
        "column": column + 1,
        "landing_cell": {"row": row + 1, "column": column + 1},
        "board_after": board_state(after),
        "wins_now": wins_now,
        "opponent_winning_replies": [reply + 1 for reply in opponent_winning_replies],
        "your_winning_columns_next": [reply + 1 for reply in your_winning_columns_next],
        "blocks_current_opponent_wins": [threat + 1 for threat in blocked],
        "allows_immediate_loss": not wins_now and bool(opponent_winning_replies),
    }


def board_ascii(board: list[list[str]]) -> str:
    """Render rows with explicit top/bottom and left-to-right orientation."""
    lines = ["columns  1 2 3 4 5 6 7"]
    for row_number, row in enumerate(board, start=1):
        suffix = "  <- top" if row_number == 1 else ""
        if row_number == ROWS:
            suffix = "  <- bottom"
        lines.append(f"row {row_number}:  {' '.join(row)}{suffix}")
    return "\n".join(lines)


def tactical_candidates(
    board: list[list[str]],
    piece: str,
    opponent: str,
) -> tuple[list[int], str]:
    """Return tactically admissible zero-based columns and the policy reason."""
    legal = legal_columns(board)
    if not legal:
        return [], "no-legal-moves"

    immediate_wins = winning_columns(board, piece)
    if immediate_wins:
        return immediate_wins, "immediate-win"

    analyses = {column: analyze_move(board, column, piece, opponent) for column in legal}
    safe = [column for column in legal if not analyses[column]["opponent_winning_replies"]]
    opponent_wins_now = winning_columns(board, opponent)

    if opponent_wins_now and safe:
        return safe, "forced-defense"
    if safe and len(safe) < len(legal):
        return safe, "avoid-immediate-loss"
    if not safe:
        return legal, "forced-loss-or-no-safe-one-ply-move"
    return legal, "strategic-choice"


def build_jev_state(
    board: list[list[str]],
    candidate_columns: list[int],
    candidate_reason: str,
) -> dict[str, object]:
    """Build the exact tactical state supplied to Jev for a move."""
    your_wins = winning_columns(board, JEV_PIECE)
    opponent_wins = winning_columns(board, HUMAN)
    legal = legal_columns(board)
    analyses = {str(column + 1): analyze_move(board, column, JEV_PIECE, HUMAN) for column in legal}

    return {
        "game": "Connect Four",
        "perspective": {
            "you": {"name": "Jev", "piece": JEV_PIECE},
            "opponent": {"name": "human", "piece": HUMAN},
            "turn": {"name": "Jev", "piece": JEV_PIECE},
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
            "your_winning_columns_now": [column + 1 for column in your_wins],
            "opponent_winning_columns_now": [column + 1 for column in opponent_wins],
            "candidate_reason": candidate_reason,
            "candidate_columns": [column + 1 for column in candidate_columns],
        },
        "move_analysis": analyses,
        "rules": [
            "Four equal pieces horizontally, vertically, or diagonally wins immediately.",
            "Only listed legal columns may be played.",
            "The supplied tactical facts were computed exactly by the game engine.",
        ],
    }


def jev_choices(
    board: list[list[str]],
    candidates: list[int],
) -> dict[str, dict[str, object]]:
    """Build structured Choice criteria for the supplied candidate columns."""
    return {str(column + 1): analyze_move(board, column, JEV_PIECE, HUMAN) for column in candidates}


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


def choose_jev_column(
    jev: Jev,
    board: list[list[str]],
    *,
    candidates: list[int] | None = None,
    reason: str | None = None,
) -> tuple[int, ChoiceResult | None, str]:
    """Choose a move, bypassing Jev when Python proves only one candidate."""
    if candidates is None or reason is None:
        candidates, reason = tactical_candidates(board, JEV_PIECE, HUMAN)

    if not candidates:
        raise RuntimeError("no Jev move available")
    if len(candidates) == 1:
        return candidates[0], None, reason

    result = jev.choice(
        QUESTION,
        state=build_jev_state(board, candidates, reason),
        choices=jev_choices(board, candidates),
    )

    try:
        column = int(result.value) - 1
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Jev returned a non-numeric column: {result.value!r}") from exc

    if column not in candidates:
        raise RuntimeError(f"Jev returned a non-candidate column: {result.value!r}")

    return column, result, reason


def print_tactical_scan(board: list[list[str]], candidates: list[int], reason: str) -> None:
    """Print a compact explanation of Python's tactical preprocessing."""
    immediate_jev_wins = winning_columns(board, JEV_PIECE)
    immediate_human_wins = winning_columns(board, HUMAN)
    print("\nJev tactical scan:")
    print("  immediate Jev wins: " + (" ".join(str(column + 1) for column in immediate_jev_wins) or "none"))
    if immediate_human_wins:
        print("  immediate human wins: " + " ".join(str(column + 1) for column in immediate_human_wins))
    if reason == "forced-defense":
        print("  safe candidates: " + " ".join(str(column + 1) for column in candidates))
    elif reason == "forced-loss-or-no-safe-one-ply-move":
        print("  no one-ply-safe move exists; all legal columns remain")
    elif len(candidates) > 1:
        print("  Jev is thinking over columns: " + " ".join(str(column + 1) for column in candidates))


def print_forced_jev_move(column: int, reason: str) -> None:
    """Explain a deterministic move that did not require a Jev call."""
    label = "winning move" if reason == "immediate-win" else "move"
    print(f"\nJev forced {label}: column {column + 1}")
    print("(no model call: only one tactically valid move)")


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


def main() -> None:
    """Run an interactive human-versus-Jev Connect Four game."""
    board = new_board()
    last_move: tuple[str, int] | None = None

    print("=== Connect Four: you vs Jev ===")
    print("Get four in a row horizontally, vertically, or diagonally.")
    print("Enter a column number 1-7. Enter q to quit.")
    print()

    try:
        with Jev() as jev:
            while True:
                print(render_board(board, turn_piece=HUMAN, last_move=last_move))
                human_column = prompt_human_column(board)
                if human_column is None:
                    print("Game ended.")
                    return

                drop_piece(board, human_column, HUMAN)
                last_move = (HUMAN, human_column)
                if has_four(board, HUMAN):
                    print()
                    print(render_board(board, turn_piece=None, last_move=last_move))
                    print("\nYou win!")
                    return

                if not legal_columns(board):
                    print()
                    print(render_board(board, turn_piece=None, last_move=last_move))
                    print("\nDraw: the board is full.")
                    return

                print()
                print(render_board(board, turn_piece=JEV_PIECE, last_move=last_move))
                candidates, reason = tactical_candidates(board, JEV_PIECE, HUMAN)
                print_tactical_scan(board, candidates, reason)
                jev_column, result, reason = choose_jev_column(
                    jev,
                    board,
                    candidates=candidates,
                    reason=reason,
                )
                if result is None:
                    print_forced_jev_move(jev_column, reason)
                else:
                    print_jev_result(result, reason, legal_columns(board), candidates)

                drop_piece(board, jev_column, JEV_PIECE)
                last_move = (JEV_PIECE, jev_column)
                if has_four(board, JEV_PIECE):
                    print()
                    print(render_board(board, turn_piece=None, last_move=last_move))
                    print("\nJev wins!")
                    return

                if not legal_columns(board):
                    print()
                    print(render_board(board, turn_piece=None, last_move=last_move))
                    print("\nDraw: the board is full.")
                    return
    except KeyboardInterrupt:
        print("\nGame ended.")


if __name__ == "__main__":
    main()
