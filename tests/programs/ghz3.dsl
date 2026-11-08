# three-qubit GHZ state (|000>+|111>)/sqrt2
qubit q[3]
qubitop1 q[0] = H
qubitop2 q[0],q[1] = CN
qubitop2 q[1],q[2] = CN
print(q)
end
