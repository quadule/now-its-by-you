"""Harvest: reduce this machine's context to a voice vector (milestone 3).

Each local signal collapses to a handful of floats before it touches anything
else; raw captures are deleted after reduction and never leave this module.

    harvest(opt_out: set[str]) -> Voice
"""
