# extra text after an otherwise valid gate name
# expect_error: Syntax Error
qubit q[1]
qubitop1 q[0] = H junk
end
