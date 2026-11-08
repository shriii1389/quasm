# name: 400 fair coin flips, driven by a loop instead of 800 lines
# expect_freq: 1 0.5 0.08
qubit a[1]
repeat 400
qubitop1 a[0] = H
measure a[0]
endrepeat
end
