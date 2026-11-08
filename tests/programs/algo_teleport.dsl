# name: teleportation: the corrected third qubit holds the prepared state, whatever was measured
seed 99
repeat 12
qubit q[3]
qubitop1 q[0] = H
qubitop1 q[0] = T
qubitop1 q[0] = H
qubitop1 q[0] = S
qubitop1 q[0] = SN
qubitop1 q[1] = H
qubitop2 q[1],q[2] = CN
qubitop2 q[0],q[1] = CN
qubitop1 q[0] = H
measure q[0] -> a
measure q[1] -> b
if b == 1
qubitop1 q[2] = X
endif
if a == 1
qubitop1 q[2] = Z
endif
print(q)
endrepeat
end
