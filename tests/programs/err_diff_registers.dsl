# a two-qubit gate spanning two separate registers
# expect_error: Two-qubit gate operands must be one register
qubit a[1]
qubit b[1]
qubitop2 a[0],b[0] = CN
end
