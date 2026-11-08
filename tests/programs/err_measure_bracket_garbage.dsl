# name: nothing may touch the closing bracket of a measured qubit but a space or the arrow
# expect_error: Syntax Error
qubit q[1]
measure q[0]x
end
