# 50 trials of a biased qubit: |q> = 0.866|0> + 0.5|1>, so p(1) = 0.25.
# No single gate can reprepare a biased state from a collapsed one, so each
# trial redeclares the register -- redeclaring at the same size reuses the
# same storage, which is what makes a loop like this able to run forever.
repeat 50
qubit q = [(0.8660254,0),(0.5,0)]
measure q[0]
endrepeat
end
