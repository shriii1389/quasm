# name: QFT on |000> is the uniform superposition
# The textbook 3-qubit QFT: H and controlled phases on each qubit in turn,
# then a swap to undo the bit reversal the algorithm leaves behind.
qubit q[3]
qubitop1 q[0] = H
qubitop2 q[1],q[0] = CP2
qubitop2 q[2],q[0] = CP3
qubitop1 q[1] = H
qubitop2 q[2],q[1] = CP2
qubitop1 q[2] = H
qubitop2 q[0],q[2] = SW
print(q)
end
