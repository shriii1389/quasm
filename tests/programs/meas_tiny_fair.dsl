# name: a fair coin with amplitudes near 1e-6 is still a fair coin
# expect_freq: 1 0.5 0.12
seed 7
repeat 200
qubit b = [(0.000001,0),(0.000001,0)]
measure b[0]
endrepeat
end
