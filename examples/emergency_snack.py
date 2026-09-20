"""Use a direct Python Choice for a mildly urgent snack decision."""

from pyjev import Jev


def main() -> None:
    state = {
        "incident": "The service is degraded and the on-call engineer has skipped lunch.",
        "constraints": ["portable", "not sticky", "available at a nearby shop"],
    }
    with Jev() as jev:
        result = jev.choice(
            "Which snack should the on-call engineer bring?",
            state=state,
            choices={
                "fruit": "Portable fruit that will not make the keyboard sticky",
                "pretzels": "A salty snack that survives a long incident",
                "chocolate": "A morale boost for the person holding the pager",
            },
        )
    print(f"choice={result.value} confidence={result.confidence:.2f}")


if __name__ == "__main__":
    main()
