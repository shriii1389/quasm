# The 3-qubit quantum Fourier transform.
#
# QFT|j> spreads j uniformly across all basis states, giving amplitude k the
# phase exp(2*pi*i*j*k/8). The controlled-phase gates CP2 and CP3 supply the
# pi/2 and pi/4 rotations; the final swap undoes the bit reversal the
# algorithm leaves behind.
#
# Change the X below to pick a different input: no X gives |000>, X on q[2]
# gives |001>, X on q[1] gives |010>, and so on.

qubit q[3]
qubitop1 q[2] = X              # input |001>, i.e. j = 1

qubitop1 q[0] = H
qubitop2 q[1],q[0] = CP2
qubitop2 q[2],q[0] = CP3

qubitop1 q[1] = H
qubitop2 q[2],q[1] = CP2

qubitop1 q[2] = H

qubitop2 q[0],q[2] = SW        # undo the bit reversal

print(q)                       # eight amplitudes of modulus 1/sqrt(8) = 0.3536,
                               # each rotated one eighth of a turn from the last
end
