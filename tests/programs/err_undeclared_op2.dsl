# two-qubit gate on an undeclared name
# expect_error: Variable not declared
qubit q[2]
qubitop2 z[0],q[1] = CN
end
