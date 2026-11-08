# name: whole-register measurement of an 8-way superposition gives each outcome 1/8
# expect_freq: 000 0.125 0.06
seed 5
repeat 400
qubit q[3]
qubitop1 q[0] = H
qubitop1 q[1] = H
qubitop1 q[2] = H
measure q
endrepeat
end
