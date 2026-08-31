from dataclasses import dataclass


# Store the headline metadata and original source for a Rotoworld update.
@dataclass(frozen=True, slots=True)
class PlayerNewsModel:
    title: str
    date: str
    author: str
    source_url: str
