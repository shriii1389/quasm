# name: punctuation between Z and a is not a variable name
# expect_error: Syntax Error
qubit q[1]
measure q[0] -> ]
end
