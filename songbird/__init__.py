"""Songbird: a folk song whose artifact is the program that sings it."""

# The program's version, written into every record it makes (`program_version`). 0.1.0 sang the first version of the
# song; 0.2.0 is the program as the performance version carries it.
__version__ = "0.2.0"

# The record's format: the number a record says it was written in (`record_format`; a record without one is 1, as
# the first version's is). It goes up only when a record changes so that an older program would misread it, never
# for a field added, which older programs pass over. A program meeting a higher number than its own says so, and
# sings from what it understands of the record (cli.newer_than_this).
RECORD_FORMAT = 2
