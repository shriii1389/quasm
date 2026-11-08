# name: fidelity decays as (1 + (1 - 4p/3)^N)/2 over N noisy gates
# expect_freq: 0 0.62 0.10
# Ten identity gates at p = 0.1: the Bloch z component shrinks by (1 - 4p/3)
# each time, so P(|0>) = (1 + 0.8667^10)/2 = 0.6195.
noise 0.1
repeat 300
qubit q[1]
repeat 10
qubitop1 q[0] = I
endrepeat
measure q[0]
endrepeat
end
