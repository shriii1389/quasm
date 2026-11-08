# name: a block the program never closes is reported, even after an inner end
# expect_error: Unexpected end of input
qubit q[1]
repeat 2
qubitop1 q[0] = X
end
