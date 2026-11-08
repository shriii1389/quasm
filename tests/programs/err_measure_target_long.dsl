# name: a measurement target is one letter, so -> cd is not a target
# expect_error: Syntax Error
qubit q[1]
measure q[0] -> cd
end
