# four-qubit GHZ state
qubit q[4]
qubitop1 q[0] = H
qubitop2 q[0],q[1] = CN
qubitop2 q[1],q[2] = CN
qubitop2 q[2],q[3] = CN
print(q)
end
