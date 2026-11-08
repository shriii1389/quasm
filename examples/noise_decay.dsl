# Fidelity decay under a depolarising channel.
#
# `noise p` gives every qubit a probability p of being hit by a random Pauli
# after each gate it takes part in. X and Y flip |0>, Z does not, so a single
# gate flips the qubit with probability 2p/3.
#
# Over N gates the Bloch z component shrinks by (1 - 4p/3) each time, so
#     P(|0>) = (1 + (1 - 4p/3)^N) / 2
# which for p = 0.1 and N = 10 is 0.6195. Count the 0s below: about 62% of 300.
#
# One run is one quantum trajectory. The channel is what the ensemble over
# many runs converges to -- which is also how you measure a real device.

noise 0.1

repeat 300
qubit q[1]
repeat 10
qubitop1 q[0] = I              # an identity gate is still an opportunity to decohere
endrepeat
measure q[0]
endrepeat
end
