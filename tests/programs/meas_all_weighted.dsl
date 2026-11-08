# name: whole-register measurement follows unequal weights 0.1, 0.2, 0.3, 0.4 over four outcomes
# expect_freq: 11 0.4 0.08
seed 9
repeat 400
qubit q = [(0.31622777,0),(0.4472136,0),(0.54772256,0),(0.63245553,0)]
measure q
endrepeat
end
