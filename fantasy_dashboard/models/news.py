from dataclasses import dataclass


# Store the small portion of a Rotoworld update shown in the roster dialog.
@dataclass(frozen=True, slots=True)
class PlayerNewsModel:
    title: str
    date: str
    text: str
