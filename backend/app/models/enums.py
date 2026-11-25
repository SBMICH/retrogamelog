import enum


class GameStatus(str, enum.Enum):
    playing = "playing"
    backlog = "backlog"
    completed = "completed"
    dropped = "dropped"


class LogKind(str, enum.Enum):
    started = "started"
    completed = "completed"
    dropped = "dropped"
    replayed = "replayed"
    note = "note"


class Performance(str, enum.Enum):
    perfect = "perfect"
    playable = "playable"
    issues = "issues"
    unplayable = "unplayable"
