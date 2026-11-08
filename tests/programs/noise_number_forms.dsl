# name: noise rates take the same number forms, and 0e0 turns the channel off
noise 1.
noise 0e0
qubit q[1]
qubitop1 q[0] = H
print(q)
end
