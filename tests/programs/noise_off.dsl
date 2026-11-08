# name: noise 0 leaves the channel off entirely
noise 0
qubit q[2]
qubitop1 q[0] = H
qubitop2 q[0],q[1] = CN
print(q)
end
