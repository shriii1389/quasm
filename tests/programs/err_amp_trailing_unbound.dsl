# a malformed fresh declaration must never bind the name -- q stays
# undeclared, it does not silently become usable despite the reported error
# expect_error: Variable not declared
qubit q = [(1,0),(0,0)] junk
qubitop1 q[0] = X
end
