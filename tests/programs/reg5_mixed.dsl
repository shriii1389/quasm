# mixed gates across a 5-qubit register
qubit q[5]
qubitop1 q[0] = H
qubitop1 q[4] = X
qubitop2 q[0],q[4] = CN
qubitop1 q[2] = H
print(q)
end
