# name: QFT on |0101> of a 4-qubit register
qubit q[4]
qubitop1 q[1] = X
qubitop1 q[3] = X
qubitop1 q[0] = H
qubitop2 q[1],q[0] = CP2
qubitop2 q[2],q[0] = CP3
qubitop2 q[3],q[0] = CP4
qubitop1 q[1] = H
qubitop2 q[2],q[1] = CP2
qubitop2 q[3],q[1] = CP3
qubitop1 q[2] = H
qubitop2 q[3],q[2] = CP2
qubitop1 q[3] = H
qubitop2 q[0],q[3] = SW
qubitop2 q[1],q[2] = SW
print(q)
end
