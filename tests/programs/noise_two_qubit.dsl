# name: a two-qubit gate exposes both of its qubits to the channel
# expect_freq: 00 0.64 0.10
# CN leaves |00> alone, then noises control and target independently. Each
# flips with probability 2p/3 = 0.2, so both survive with probability
# (1 - 0.2)^2 = 0.64.
noise 0.3
repeat 300
qubit q[2]
qubitop2 q[0],q[1] = CN
measure q
endrepeat
end
