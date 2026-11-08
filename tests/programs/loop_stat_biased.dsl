# name: 300 trials at p(1) = 0.25, redeclaring the register each time
# expect_freq: 1 0.25 0.08
repeat 300
qubit a = [(0.8660254,0),(0.5,0)]
measure a[0]
endrepeat
end
