# name: depolarising at p flips a qubit with probability 2p/3
# expect_freq: 1 0.20 0.09
# X and Y flip |0>, Z leaves it alone, so one gate at p = 0.3 reads 1 with
# probability 2 * 0.3 / 3 = 0.2.
noise 0.3
repeat 300
qubit q[1]
qubitop1 q[0] = I
measure q[0]
endrepeat
end
