# name: QFT on |001> gives the k-th root of unity in every amplitude
qubit q[3]
qubitop1 q[2] = X
qubitop1 q[0] = H
qubitop2 q[1],q[0] = CP2
qubitop2 q[2],q[0] = CP3
qubitop1 q[1] = H
qubitop2 q[2],q[1] = CP2
qubitop1 q[2] = H
qubitop2 q[0],q[2] = SW
print(q)
end
