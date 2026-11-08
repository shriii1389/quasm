# H then CNOT makes the Bell state (|00>+|11>)/sqrt2
qubit q[2]
qubitop1 q[0] = H
qubitop2 q[0],q[1] = CN
print(q)
end
