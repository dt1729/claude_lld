"""Language-neutral analysis: reachability, duplication, and the metrics over them.

Nothing here knows what Python is beyond the parser it is handed. A call is a call, a
reachable set is a reachable set, and a Jaccard overlap is arithmetic. The parts that do
know a language - how to find a call, where a program starts - live one level out in the
adapter, which is the seam this package is built around.

The order matters and it is not the order the old detectors used. Reachability comes first,
because a finding has no weight until you know whether the code it is about runs at all:
duplication across two independent features is the complaint this plugin exists for, the
same duplication inside one feature is a note, and duplication where one copy is unreachable
is a deletion.
"""
