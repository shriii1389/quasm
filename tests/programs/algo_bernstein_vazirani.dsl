# name: Bernstein-Vazirani recovers the secret 101 in one query, with certainty
qubit q[4]
qubitop1 q[3] = X
qubitop1 q[0] = H
qubitop1 q[1] = H
qubitop1 q[2] = H
qubitop1 q[3] = H
qubitop2 q[0],q[3] = CN
qubitop2 q[2],q[3] = CN
qubitop1 q[0] = H
qubitop1 q[1] = H
qubitop1 q[2] = H
measure q[0] -> a
measure q[1] -> b
measure q[2] -> c
qubit r[1]
if a == 1
if b == 0
if c == 1
qubitop1 r[0] = X
endif
endif
endif
print(r)
end
