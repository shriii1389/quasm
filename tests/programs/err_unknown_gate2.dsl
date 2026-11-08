# a two-qubit gate name that does not exist
# expect_error: Syntax Error
qubit q[2]
qubitop2 q[0],q[1] = QQ
end
