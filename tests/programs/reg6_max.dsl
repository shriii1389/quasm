# the largest register the interpreter allows
qubit q[6]
qubitop1 q[0] = H
qubitop1 q[5] = X
qubitop2 q[0],q[5] = CZ
print(q)
end
