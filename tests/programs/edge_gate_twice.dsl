# the same qubit can be targeted repeatedly
qubit q[2]
qubitop1 q[0] = H
qubitop1 q[0] = H
print(q)
end
