# name: two-qubit Grover finds the marked |11> in one iteration, with certainty
qubit g[2]
qubitop1 g[0] = H
qubitop1 g[1] = H
qubitop2 g[0],g[1] = CZ
qubitop1 g[0] = H
qubitop1 g[1] = H
qubitop1 g[0] = X
qubitop1 g[1] = X
qubitop2 g[0],g[1] = CZ
qubitop1 g[0] = X
qubitop1 g[1] = X
qubitop1 g[0] = H
qubitop1 g[1] = H
print(g)
measure g -> m
print(g)
end
